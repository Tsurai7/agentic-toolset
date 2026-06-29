// Package mcpmerge ports providers/shared/merge-mcp.py. It resolves the managed
// MCP integration fragments (per-machine tool paths + __KEY__ placeholder
// substitution) and either merges them into a provider mcp.json (Cursor),
// preserving hand-added servers, or registers them at Claude Code user scope via
// the `claude` CLI (the file Claude Code actually reads).
//
// Order-preserving output uses the stdlib-backed jsonorder; the leaf payload sent
// to `claude mcp add-json` is marshaled with sonic (the idiomatic hot/leaf path).
package mcpmerge

import (
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"github.com/bytedance/sonic"

	"github.com/Tsurai7/agentic-cfg/internal/jsonorder"
)

// LoadEnv resolves tool locations on THIS machine (rather than hardcoding paths),
// then applies secrets/.env overrides (with ~ expansion). Mirrors load_env().
func LoadEnv(root string) map[string]string {
	env := map[string]string{
		"NPX":               firstNonEmpty(os.Getenv("NPX"), which("npx", "npx")),
		"PATH":              firstNonEmpty(os.Getenv("PATH"), "/usr/local/bin:/usr/bin:/bin"),
		"NODE_PATH":         firstNonEmpty(os.Getenv("NODE_PATH"), nodePath()),
		"LEAN_CTX":          firstNonEmpty(os.Getenv("LEAN_CTX"), which("lean-ctx", "lean-ctx")),
		"LEAN_CTX_DATA_DIR": firstNonEmpty(os.Getenv("LEAN_CTX_DATA_DIR"), expandHome("~/.lean-ctx")),
	}
	if b, err := os.ReadFile(filepath.Join(root, "secrets", ".env")); err == nil {
		for _, line := range strings.Split(string(b), "\n") {
			line = strings.TrimSpace(line)
			if line == "" || strings.HasPrefix(line, "#") || !strings.Contains(line, "=") {
				continue
			}
			k, v, _ := strings.Cut(line, "=")
			v = strings.TrimSpace(v)
			v = strings.Trim(v, `"`)
			v = strings.Trim(v, `'`)
			env[strings.TrimSpace(k)] = expandHome(v)
		}
	}
	return env
}

// unresolvedLauncherWarning returns a warning when npx cannot be resolved on this
// machine, so a "successful" install does not silently leave a dead MCP server
// (BUG-13). npxValue is the resolved NPX env value; npxFound is whether npx was
// actually located on PATH. Empty result ⇒ npx is fine.
func unresolvedLauncherWarning(npxValue string, npxFound bool) string {
	if !npxFound && (npxValue == "" || npxValue == "npx") {
		return "merge-mcp: WARNING npx not found on PATH — managed MCP servers that use it " +
			"(e.g. gitnexus) will not launch until you install Node/npx (e.g. `brew install node`)"
	}
	return ""
}

func warnIfNpxMissing(env map[string]string) {
	_, err := exec.LookPath("npx")
	if msg := unresolvedLauncherWarning(env["NPX"], err == nil); msg != "" {
		fmt.Fprintln(os.Stderr, msg)
	}
}

func which(name, fallback string) string {
	if p, err := exec.LookPath(name); err == nil {
		return p
	}
	return fallback
}

func nodePath() string {
	if out, err := exec.Command("npm", "root", "-g").Output(); err == nil { //nolint:noctx // one-shot synchronous subprocess; no cancellation context flows through this CLI path
		if s := strings.TrimSpace(string(out)); s != "" {
			return s
		}
	}
	return os.Getenv("NODE_PATH")
}

func expandHome(s string) string {
	if s == "~" || strings.HasPrefix(s, "~/") {
		if h, err := os.UserHomeDir(); err == nil {
			if s == "~" {
				return h
			}
			return filepath.Join(h, s[2:])
		}
	}
	return s
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if v != "" {
			return v
		}
	}
	return ""
}

var placeholderRe = regexp.MustCompile(`__([A-Z0-9_]+)__`)

// substitute replaces __KEY__ tokens in every string leaf (recursively), like
// the Python substitute(). Object keys are left untouched. A single regex pass
// resolves each placeholder exactly once from the original text, so a resolved
// value that itself contains a __TOKEN__ is never re-substituted and a key that
// is a prefix of another (__LEAN_CTX__ vs __LEAN_CTX_DATA_DIR__) cannot clobber
// it (BUG-15). Unknown placeholders are left untouched.
func substitute(v any, env map[string]string) any {
	switch t := v.(type) {
	case string:
		return placeholderRe.ReplaceAllStringFunc(t, func(m string) string {
			if val, ok := env[m[2:len(m)-2]]; ok {
				return val
			}
			return m
		})
	case map[string]any:
		for k, vv := range t {
			t[k] = substitute(vv, env)
		}
		return t
	case []any:
		for i, vv := range t {
			t[i] = substitute(vv, env)
		}
		return t
	}
	return v
}

// excludedServers reads AGENTIC_MCP_EXCLUDE (comma-separated server names). The weak
// install tier sets this to omit the orientation-inducing layer (e.g. lean-ctx).
func excludedServers() map[string]bool {
	m := map[string]bool{}
	for _, n := range strings.Split(os.Getenv("AGENTIC_MCP_EXCLUDE"), ",") {
		if n = strings.TrimSpace(n); n != "" {
			m[n] = true
		}
	}
	return m
}

// collectFragments collects every integrations/**/mcp*.json server entry into one
// order-preserving map (sorted by path, later same-named entries win), skipping any
// server named in AGENTIC_MCP_EXCLUDE.
func collectFragments(integrationsDir string) (*jsonorder.Map, error) {
	excluded := excludedServers()
	var files []string
	_ = filepath.WalkDir(integrationsDir, func(p string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil //nolint:nilerr // best-effort walk: skip unreadable entries and keep walking
		}
		if strings.HasPrefix(d.Name(), "mcp") && strings.HasSuffix(d.Name(), ".json") {
			files = append(files, p)
		}
		return nil
	})
	sort.Strings(files)
	out := jsonorder.New()
	for _, f := range files {
		m, err := jsonorder.ReadFile(f)
		if err != nil {
			return nil, fmt.Errorf("merge-mcp: invalid JSON in %s: %w", f, err)
		}
		raw, ok := m.GetRaw("mcpServers")
		if !ok {
			// A fragment must wrap its servers in an mcpServers key. Treating a
			// bare/typo'd top-level map as the server set silently injected junk
			// servers (BUG-16); warn and skip instead.
			fmt.Fprintf(os.Stderr, "merge-mcp: WARNING %s has no \"mcpServers\" object — skipping (a fragment must wrap its servers in an mcpServers key)\n", f)
			continue
		}
		servers := jsonorder.New()
		if err := json.Unmarshal(raw, servers); err != nil {
			return nil, fmt.Errorf("merge-mcp: invalid JSON in %s: %w", f, err)
		}
		for _, name := range servers.Keys() {
			if excluded[name] {
				continue
			}
			raw, _ := servers.GetRaw(name)
			out.SetRaw(name, raw)
		}
	}
	return out, nil
}

// resolveManaged returns the managed servers (overlay + fragments) with
// placeholders substituted. includeOverlay adds the Cursor overlay as a base.
func resolveManaged(root string, includeOverlay bool) (*jsonorder.Map, error) {
	env := LoadEnv(root)
	managed := jsonorder.New()
	if includeOverlay {
		if m, err := jsonorder.ReadFile(filepath.Join(root, "providers", "cursor", "mcp.overlay.json")); err == nil {
			if raw, ok := m.GetRaw("mcpServers"); ok {
				servers := jsonorder.New()
				_ = json.Unmarshal(raw, servers)
				for _, n := range servers.Keys() {
					r, _ := servers.GetRaw(n)
					managed.SetRaw(n, r)
				}
			}
		}
	}
	frags, err := collectFragments(filepath.Join(root, "integrations"))
	if err != nil {
		return nil, err
	}
	for _, n := range frags.Keys() {
		r, _ := frags.GetRaw(n)
		managed.SetRaw(n, r)
	}
	return substituteServers(managed, env), nil
}

func substituteServers(servers *jsonorder.Map, env map[string]string) *jsonorder.Map {
	out := jsonorder.New()
	for _, name := range servers.Keys() {
		raw, _ := servers.GetRaw(name)
		var v any
		_ = json.Unmarshal(raw, &v)
		nb, _ := json.Marshal(substitute(v, env))
		out.SetRaw(name, nb)
	}
	return out
}

// MergeCursor merges the managed servers into the mcp.json at outPath, preserving
// any hand-added servers (and other top-level keys). Repo-managed servers win.
func MergeCursor(root, outPath string) error {
	warnIfNpxMissing(LoadEnv(root))
	managed, err := resolveManaged(root, true)
	if err != nil {
		return err
	}
	out := jsonorder.New()
	if b, err := os.ReadFile(outPath); err == nil {
		if err := json.Unmarshal(b, out); err != nil {
			return fmt.Errorf("merge-mcp: invalid JSON in %s: %w", outPath, err)
		}
	}
	servers := jsonorder.New()
	if raw, ok := out.GetRaw("mcpServers"); ok {
		_ = json.Unmarshal(raw, servers)
	}
	for _, n := range managed.Keys() {
		r, _ := managed.GetRaw(n)
		servers.SetRaw(n, r)
	}
	sb, _ := json.Marshal(servers)
	out.SetRaw("mcpServers", sb)
	return jsonorder.WriteFile(outPath, out)
}

var claudeServerKeys = map[string]bool{
	"command": true, "args": true, "env": true, "type": true, "url": true, "headers": true,
}

// filterClaudeConfig keeps only the fields Claude Code understands (drops e.g.
// Cursor's autoApprove). The payload is marshaled with sonic.
func filterClaudeConfig(raw json.RawMessage) ([]byte, error) {
	var cfg map[string]any
	if err := sonic.Unmarshal(raw, &cfg); err != nil {
		return nil, err
	}
	filtered := map[string]any{}
	for k, v := range cfg {
		if claudeServerKeys[k] {
			filtered[k] = v
		}
	}
	return sonic.Marshal(filtered)
}

// RegisterClaudeUser registers the managed servers at Claude Code user scope via
// the `claude` CLI, which writes ~/.claude.json (PORT-03). Idempotent: each server
// is removed then re-added. No-op with a warning if `claude` is absent.
func RegisterClaudeUser(root string) error {
	claude, err := exec.LookPath("claude")
	if err != nil {
		fmt.Fprintln(os.Stderr, "merge-mcp: 'claude' CLI not on PATH — skipping user-scope MCP registration")
		return nil //nolint:nilerr // optional dependency: skip user-scope registration when the 'claude' CLI is absent
	}
	warnIfNpxMissing(LoadEnv(root))
	managed, err := resolveManaged(root, false)
	if err != nil {
		return err
	}
	dry := os.Getenv("DRY_RUN") == "1"
	var done []string
	for _, name := range managed.Keys() {
		raw, _ := managed.GetRaw(name)
		payload, err := filterClaudeConfig(raw)
		if err != nil {
			return fmt.Errorf("merge-mcp: bad config for %s: %w", name, err)
		}
		if dry {
			fmt.Printf("[dry-run] claude mcp add-json %s <json> --scope user\n", name)
			done = append(done, name)
			continue
		}
		_ = exec.Command(claude, "mcp", "remove", name, "--scope", "user").Run()                                                        //nolint:noctx // one-shot synchronous CLI call; no cancellation context flows here
		if out, err := exec.Command(claude, "mcp", "add-json", name, string(payload), "--scope", "user").CombinedOutput(); err != nil { //nolint:noctx // one-shot synchronous CLI call; no cancellation context flows here
			return fmt.Errorf("merge-mcp: failed to register %s: %s", name, strings.TrimSpace(string(out)))
		}
		done = append(done, name)
	}
	sort.Strings(done)
	fmt.Printf("Registered %d Claude user-scope MCP server(s): %s\n", len(done), join(done))
	return nil
}

// ManagedServerNames returns the names of the MCP servers this repo manages
// (integration fragments, placeholders resolved), sorted. Used by `agentic eject`
// to know exactly which user-scope servers to remove, and unit-testable without
// the `claude` CLI.
func ManagedServerNames(root string) ([]string, error) {
	managed, err := resolveManaged(root, false)
	if err != nil {
		return nil, err
	}
	names := append([]string(nil), managed.Keys()...)
	sort.Strings(names)
	return names, nil
}

// RemoveClaudeUser removes the managed servers from Claude Code user scope via the
// `claude` CLI (the inverse of RegisterClaudeUser). Best-effort and idempotent: a
// server already absent is fine. No-op with a warning if `claude` is absent.
func RemoveClaudeUser(root string) error {
	claude, err := exec.LookPath("claude")
	if err != nil {
		fmt.Fprintln(os.Stderr, "merge-mcp: 'claude' CLI not on PATH — skipping user-scope MCP removal")
		return nil //nolint:nilerr // optional dependency: skip when the 'claude' CLI is absent
	}
	names, err := ManagedServerNames(root)
	if err != nil {
		return err
	}
	dry := os.Getenv("DRY_RUN") == "1"
	for _, name := range names {
		if dry {
			fmt.Printf("[dry-run] claude mcp remove %s --scope user\n", name)
			continue
		}
		_ = exec.Command(claude, "mcp", "remove", name, "--scope", "user").Run() //nolint:noctx // one-shot synchronous CLI call
	}
	fmt.Printf("Removed %d Claude user-scope MCP server(s): %s\n", len(names), join(names))
	return nil
}

func join(ss []string) string {
	if len(ss) == 0 {
		return "none"
	}
	return strings.Join(ss, ", ")
}
