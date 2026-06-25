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
	"sort"
	"strings"

	"github.com/Tsurai7/agentic-cfg/internal/jsonorder"
	"github.com/bytedance/sonic"
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

func which(name, fallback string) string {
	if p, err := exec.LookPath(name); err == nil {
		return p
	}
	return fallback
}

func nodePath() string {
	if out, err := exec.Command("npm", "root", "-g").Output(); err == nil {
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

// substitute replaces __KEY__ tokens in every string leaf (recursively), like
// the Python substitute(). Object keys are left untouched.
func substitute(v any, env map[string]string) any {
	switch t := v.(type) {
	case string:
		for k, val := range env {
			t = strings.ReplaceAll(t, "__"+k+"__", val)
		}
		return t
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

// collectFragments collects every integrations/**/mcp*.json server entry into one
// order-preserving map (sorted by path, later same-named entries win).
func collectFragments(integrationsDir string) (*jsonorder.Map, error) {
	var files []string
	_ = filepath.WalkDir(integrationsDir, func(p string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
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
		servers := m
		if raw, ok := m.GetRaw("mcpServers"); ok {
			servers = jsonorder.New()
			if err := json.Unmarshal(raw, servers); err != nil {
				return nil, fmt.Errorf("merge-mcp: invalid JSON in %s: %w", f, err)
			}
		}
		for _, name := range servers.Keys() {
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
		return nil
	}
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
		_ = exec.Command(claude, "mcp", "remove", name, "--scope", "user").Run()
		if out, err := exec.Command(claude, "mcp", "add-json", name, string(payload), "--scope", "user").CombinedOutput(); err != nil {
			return fmt.Errorf("merge-mcp: failed to register %s: %s", name, strings.TrimSpace(string(out)))
		}
		done = append(done, name)
	}
	sort.Strings(done)
	fmt.Printf("Registered %d Claude user-scope MCP server(s): %s\n", len(done), join(done))
	return nil
}

func join(ss []string) string {
	if len(ss) == 0 {
		return "none"
	}
	return strings.Join(ss, ", ")
}
