// Package lifecycle implements `agentic inject` and `agentic eject`: a single,
// reversible, test-covered way to add the agentic-cfg footprint to a Claude
// config and to remove it again without disturbing the user's own content.
//
// Inject mirrors providers/claude/install.sh (skills symlink, generated CLAUDE.md
// @import block, hooks + permissions in settings.json, and best-effort user-scope
// MCP registration). Eject reverses exactly those, preserving hand-written user
// content. Every filesystem step is parametrized by Root (the repo) and Home (the
// target ~), so the whole thing is unit-testable against a temp dir; the only
// non-testable step is MCP, which needs the external `claude` CLI and is therefore
// best-effort and gated by SkipMCP.
package lifecycle

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/Tsurai7/agentic-cfg/internal/claudemd"
	"github.com/Tsurai7/agentic-cfg/internal/mcpmerge"
	"github.com/Tsurai7/agentic-cfg/internal/settings"
)

const (
	generatedName = "agentic-cfg.generated.md"
	skillsBackup  = "skills.pre-agentic"
	agentsBackup  = "agents.pre-agentic"
)

// Options configures an inject/eject run.
type Options struct {
	Root    string    // agentic-cfg repo root (contains core/, providers/, integrations/)
	Home    string    // target home directory; the Claude config lives in Home/.claude
	DryRun  bool      // print actions, change nothing
	SkipMCP bool      // skip the `claude` CLI MCP step (tests set this true)
	Log     io.Writer // progress output (defaults to os.Stdout)
}

func (o *Options) logf(format string, a ...any) {
	w := o.Log
	if w == nil {
		w = os.Stdout
	}
	fmt.Fprintf(w, format+"\n", a...)
}

func (o *Options) claudeDir() string { return filepath.Join(o.Home, ".claude") }
func (o *Options) skillsSource() string {
	return filepath.Join(o.Root, "core", "skills")
}

func (o *Options) agentsSource() string {
	return filepath.Join(o.Root, "core", "agents")
}

// GeneratedMD builds the repo-owned generated CLAUDE.md content (stub with
// __AGENTIC_ROOT__ resolved + AGENTS.md + always-on principles + user rules),
// mirroring providers/claude/install.sh:install_claude_md.
func GeneratedMD(root string) (string, error) {
	var b strings.Builder
	stub, err := os.ReadFile(filepath.Join(root, "providers", "claude", "CLAUDE.md.stub"))
	if err != nil {
		return "", err
	}
	b.WriteString(strings.ReplaceAll(string(stub), "__AGENTIC_ROOT__", root))
	agents, err := os.ReadFile(filepath.Join(root, "core", "instructions", "AGENTS.md"))
	if err != nil {
		return "", err
	}
	b.Write(agents)

	b.WriteString("\n## Principles (always-on)\n")
	princ, _ := filepath.Glob(filepath.Join(root, "core", "principles", "*.md"))
	sort.Strings(princ)
	for _, f := range princ {
		if filepath.Base(f) == "README.md" {
			continue
		}
		if c, err := os.ReadFile(f); err == nil {
			b.WriteString("\n")
			b.Write(c)
		}
	}

	b.WriteString("\n## User rules\n")
	rules, _ := filepath.Glob(filepath.Join(root, "core", "instructions", "user-rules", "*.md"))
	sort.Strings(rules)
	for _, f := range rules {
		if filepath.Base(f) == "cursor-rules-pointer.md" {
			continue
		}
		if c, err := os.ReadFile(f); err == nil {
			b.WriteString("\n### " + strings.TrimSuffix(filepath.Base(f), ".md") + "\n")
			b.Write(c)
		}
	}
	return b.String(), nil
}

// Inject adds the agentic-cfg footprint to Home/.claude, preserving user content.
// Idempotent: running it twice yields the same result.
func Inject(o Options) error {
	if err := validateRoot(o.Root); err != nil {
		return err
	}
	cd := o.claudeDir()
	if !o.DryRun {
		if err := os.MkdirAll(cd, 0o755); err != nil {
			return err
		}
	}

	if err := injectSkills(&o, cd); err != nil {
		return err
	}
	if err := injectAgents(&o, cd); err != nil {
		return err
	}

	gen := filepath.Join(cd, generatedName)
	md, err := GeneratedMD(o.Root)
	if err != nil {
		return err
	}
	if o.DryRun {
		o.logf("[dry-run] write %s; ensure @import block in %s", gen, filepath.Join(cd, "CLAUDE.md"))
	} else {
		// Atomic write: the generated file is imported by every session, so an
		// interrupt mid-write must never leave a truncated prefix silently
		// degrading future sessions (BUG-12 parity, same helper claudemd.Ensure
		// itself uses below).
		if err := claudemd.AtomicWrite(gen, []byte(md), 0o644); err != nil {
			return err
		}
		if err := claudemd.Ensure(gen, filepath.Join(cd, "CLAUDE.md")); err != nil {
			return err
		}
		o.logf("CLAUDE.md: ensured @import -> %s", gen)
	}

	frag, cleanup, err := resolvedFragment(o.Root)
	if err != nil {
		return err
	}
	defer cleanup()
	if o.DryRun {
		o.logf("[dry-run] merge hooks + permissions -> %s", filepath.Join(cd, "settings.json"))
	} else {
		if err := settings.Merge(frag, filepath.Join(cd, "settings.json")); err != nil {
			return err
		}
		o.logf("settings.json: merged managed hooks + permissions")
	}

	if o.SkipMCP {
		o.logf("MCP: skipped")
	} else if o.DryRun {
		o.logf("[dry-run] register managed MCP servers (claude CLI)")
	} else if err := mcpmerge.RegisterClaudeUser(o.Root); err != nil {
		o.logf("MCP: %v (continuing)", err)
	}
	o.logf("inject complete -> %s", cd)
	return nil
}

// Eject removes everything Inject added from Home/.claude, leaving user content
// untouched. Idempotent: safe to run when nothing is injected.
func Eject(o Options) error {
	if err := validateRoot(o.Root); err != nil {
		return err
	}
	cd := o.claudeDir()

	ejectSkills(&o, cd)
	ejectAgents(&o, cd)

	if !o.DryRun {
		if removed, err := claudemd.Remove(filepath.Join(cd, "CLAUDE.md")); err != nil {
			return err
		} else if removed {
			o.logf("CLAUDE.md: removed managed @import block")
		}
		if err := os.Remove(filepath.Join(cd, generatedName)); err == nil {
			o.logf("removed %s", generatedName)
		}
	} else {
		o.logf("[dry-run] remove managed @import block + %s", generatedName)
	}

	frag, cleanup, err := resolvedFragment(o.Root)
	if err != nil {
		return err
	}
	defer cleanup()
	if o.DryRun {
		o.logf("[dry-run] remove managed hooks + permissions from %s", filepath.Join(cd, "settings.json"))
	} else {
		if err := settings.Unmerge(frag, filepath.Join(cd, "settings.json")); err != nil {
			return err
		}
		o.logf("settings.json: removed managed hooks + permissions")
	}

	if o.SkipMCP {
		o.logf("MCP: skipped")
	} else if o.DryRun {
		o.logf("[dry-run] remove managed MCP servers (claude CLI)")
	} else if err := mcpmerge.RemoveClaudeUser(o.Root); err != nil {
		o.logf("MCP: %v (continuing)", err)
	}
	o.logf("eject complete -> %s", cd)
	return nil
}

// StatusReport summarizes the agentic-cfg footprint in a Claude config.
type StatusReport struct {
	Injected     bool   `json:"injected"` // all core pieces present
	Skills       string `json:"skills"`   // "linked" | "foreign" | "absent"
	Agents       string `json:"agents"`   // "linked" | "foreign" | "absent"
	ClaudeMDLink bool   `json:"claude_md_block"`
	GeneratedMD  bool   `json:"generated_md"`
	ManagedHooks bool   `json:"managed_hooks"`
}

// Status inspects Home/.claude and reports which inject artifacts are present.
// Read-only; safe to call any time.
func Status(o Options) StatusReport {
	cd := o.claudeDir()
	var r StatusReport

	switch fi, err := os.Lstat(filepath.Join(cd, "skills")); {
	case err != nil:
		r.Skills = "absent"
	case fi.Mode()&os.ModeSymlink != 0:
		if dest, _ := os.Readlink(filepath.Join(cd, "skills")); dest == o.skillsSource() {
			r.Skills = "linked"
		} else {
			r.Skills = "foreign"
		}
	default:
		r.Skills = "foreign"
	}

	switch fi, err := os.Lstat(filepath.Join(cd, "agents")); {
	case err != nil:
		r.Agents = "absent"
	case fi.Mode()&os.ModeSymlink != 0:
		if dest, _ := os.Readlink(filepath.Join(cd, "agents")); dest == o.agentsSource() {
			r.Agents = "linked"
		} else {
			r.Agents = "foreign"
		}
	default:
		r.Agents = "foreign"
	}

	if b, err := os.ReadFile(filepath.Join(cd, "CLAUDE.md")); err == nil {
		r.ClaudeMDLink = claudemd.BlockPresent(string(b))
	}
	if _, err := os.Stat(filepath.Join(cd, generatedName)); err == nil {
		r.GeneratedMD = true
	}
	if b, err := os.ReadFile(filepath.Join(cd, "settings.json")); err == nil {
		r.ManagedHooks = strings.Contains(string(b), "/providers/claude/hooks/")
	}

	r.Injected = r.Skills == "linked" && r.Agents == "linked" && r.ClaudeMDLink && r.GeneratedMD && r.ManagedHooks
	return r
}

// Render writes a human-readable status report to w.
func (r StatusReport) Render(w io.Writer, home string) {
	yn := func(b bool) string {
		if b {
			return "present"
		}
		return "absent"
	}
	state := "NOT injected"
	if r.Injected {
		state = "injected"
	} else if r.Skills != "absent" || r.Agents != "absent" || r.ClaudeMDLink || r.GeneratedMD || r.ManagedHooks {
		state = "PARTIAL"
	}
	fmt.Fprintf(w, "agentic-cfg status (%s/.claude)\n", home)
	fmt.Fprintf(w, "  skills          : %s\n", r.Skills)
	fmt.Fprintf(w, "  agents          : %s\n", r.Agents)
	fmt.Fprintf(w, "  CLAUDE.md block : %s\n", yn(r.ClaudeMDLink))
	fmt.Fprintf(w, "  generated md    : %s\n", yn(r.GeneratedMD))
	fmt.Fprintf(w, "  managed hooks   : %s\n", yn(r.ManagedHooks))
	fmt.Fprintf(w, "  => %s\n", state)
}

// injectLinked symlinks Home/.claude/<name> -> source. An existing symlink is
// refreshed; a real directory (user content) is backed up to Home/.claude/<backup>
// rather than clobbered. label prefixes log lines (e.g. "skills", "agents").
func injectLinked(o *Options, cd, name, source, backup, label string) error {
	target := filepath.Join(cd, name)
	fi, err := os.Lstat(target)
	switch {
	case err == nil && fi.Mode()&os.ModeSymlink != 0:
		if dest, _ := os.Readlink(target); dest == source {
			o.logf("%s: already linked -> %s", label, source)
			return nil
		}
		if !o.DryRun {
			if err := os.Remove(target); err != nil {
				return err
			}
		}
	case err == nil: // a real file/dir — preserve it
		bak := filepath.Join(cd, backup)
		o.logf("%s: backing up existing %s -> %s", label, target, bak)
		if !o.DryRun {
			if _, e := os.Lstat(bak); e == nil {
				return fmt.Errorf("inject: %s already exists; refusing to overwrite a prior backup", bak)
			}
			if err := os.Rename(target, bak); err != nil {
				return err
			}
		}
	}
	if o.DryRun {
		o.logf("[dry-run] symlink %s -> %s", target, source)
		return nil
	}
	if err := os.Symlink(source, target); err != nil {
		return err
	}
	o.logf("%s: %s -> %s", label, target, source)
	return nil
}

// ejectLinked removes the Home/.claude/<name> symlink only if it points at source,
// then restores a backup from Home/.claude/<backup> if one exists. A user's own
// real dir at <name> is never touched.
func ejectLinked(o *Options, cd, name, source, backup, label string) {
	target := filepath.Join(cd, name)
	if fi, err := os.Lstat(target); err == nil && fi.Mode()&os.ModeSymlink != 0 {
		if dest, _ := os.Readlink(target); dest == source {
			if !o.DryRun {
				_ = os.Remove(target)
			}
			o.logf("%s: removed symlink", label)
		}
	}
	bak := filepath.Join(cd, backup)
	if _, err := os.Lstat(bak); err == nil && !o.DryRun {
		if _, err := os.Lstat(target); os.IsNotExist(err) {
			if os.Rename(bak, target) == nil {
				o.logf("%s: restored backup %s", label, bak)
			}
		}
	}
}

// injectSkills symlinks Home/.claude/skills -> Root/core/skills. An existing symlink
// is refreshed; a real directory (user content) is backed up rather than clobbered.
func injectSkills(o *Options, cd string) error {
	return injectLinked(o, cd, "skills", o.skillsSource(), skillsBackup, "skills")
}

// ejectSkills removes the skills symlink only if it points at our source, then
// restores a backup if one exists. A user's own real skills dir is never touched.
func ejectSkills(o *Options, cd string) {
	ejectLinked(o, cd, "skills", o.skillsSource(), skillsBackup, "skills")
}

// injectAgents symlinks Home/.claude/agents -> Root/core/agents. An existing symlink
// is refreshed; a real directory (user content) is backed up rather than clobbered.
func injectAgents(o *Options, cd string) error {
	return injectLinked(o, cd, "agents", o.agentsSource(), agentsBackup, "agents")
}

// ejectAgents removes the agents symlink only if it points at our source, then
// restores a backup if one exists. A user's own real agents dir is never touched.
func ejectAgents(o *Options, cd string) {
	ejectLinked(o, cd, "agents", o.agentsSource(), agentsBackup, "agents")
}

// resolvedFragment writes the settings fragment with __AGENTIC_ROOT__ resolved to a
// temp file and returns its path plus a cleanup func.
func resolvedFragment(root string) (fragPath string, cleanup func(), err error) {
	raw, err := os.ReadFile(filepath.Join(root, "providers", "claude", "settings.hooks.json"))
	if err != nil {
		return "", func() {}, err
	}
	resolved := strings.ReplaceAll(string(raw), "__AGENTIC_ROOT__", root)
	tmp, err := os.CreateTemp("", "agentic-frag-*.json")
	if err != nil {
		return "", func() {}, err
	}
	if _, err := tmp.WriteString(resolved); err != nil {
		tmp.Close()
		os.Remove(tmp.Name())
		return "", func() {}, err
	}
	tmp.Close()
	return tmp.Name(), func() { os.Remove(tmp.Name()) }, nil
}

func validateRoot(root string) error {
	if root == "" {
		return errors.New("inject/eject: empty root (pass --root or run from the repo)")
	}
	if _, err := os.Stat(filepath.Join(root, "core", "skills")); err != nil {
		return fmt.Errorf("inject/eject: %s does not look like an agentic-cfg repo (no core/skills)", root)
	}
	return nil
}
