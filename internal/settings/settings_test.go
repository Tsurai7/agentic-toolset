package settings

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func write(t *testing.T, path string, v any) {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, b, 0o644); err != nil {
		t.Fatal(err)
	}
}

func read(t *testing.T, path string) map[string]any {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatalf("output is not valid JSON: %v", err)
	}
	return m
}

// eventCommands returns every hook command string under hooks[event].
func eventCommands(m map[string]any, event string) []string {
	var out []string
	hooks, _ := m["hooks"].(map[string]any)
	groups, _ := hooks[event].([]any)
	for _, g := range groups {
		gm, _ := g.(map[string]any)
		hs, _ := gm["hooks"].([]any)
		for _, h := range hs {
			hm, _ := h.(map[string]any)
			if c, ok := hm["command"].(string); ok {
				out = append(out, c)
			}
		}
	}
	return out
}

func contains(ss []string, sub string) bool {
	for _, s := range ss {
		if s == sub || (len(sub) > 0 && len(s) >= len(sub) && containsStr(s, sub)) {
			return true
		}
	}
	return false
}

func containsStr(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}

var fragment = map[string]any{
	"$schema": "https://json.schemastore.org/claude-code-settings.json",
	"hooks": map[string]any{
		"PreToolUse": []any{
			map[string]any{"matcher": "Bash|bash", "hooks": []any{
				map[string]any{"type": "command", "command": "ROOT/providers/claude/hooks/shell-guard.sh"}}},
			map[string]any{"matcher": "Read", "hooks": []any{
				map[string]any{"type": "command", "command": "lean-ctx hook redirect"}}},
		},
		"Stop": []any{
			map[string]any{"matcher": ".*", "hooks": []any{
				map[string]any{"type": "command", "command": "lean-ctx hook observe"}}}},
	},
	"permissions": map[string]any{"allow": []string{"mcp__lean-ctx__ctx_read"}},
}

func TestFreshInstall(t *testing.T) {
	d := t.TempDir()
	fp := filepath.Join(d, "frag.json")
	out := filepath.Join(d, "settings.json")
	write(t, fp, fragment)
	if err := Merge(fp, out); err != nil {
		t.Fatal(err)
	}
	m := read(t, out)
	if !contains(eventCommands(m, "PreToolUse"), "shell-guard.sh") {
		t.Error("shell-guard not registered")
	}
	if m["$schema"] == nil {
		t.Error("$schema not carried over")
	}
}

func TestNoNullSchema(t *testing.T) {
	d := t.TempDir()
	fp := filepath.Join(d, "frag.json")
	out := filepath.Join(d, "settings.json")
	write(t, fp, map[string]any{
		"hooks":       map[string]any{"PreToolUse": []any{}},
		"permissions": map[string]any{"allow": []string{}},
	})
	if err := Merge(fp, out); err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(out)
	var m map[string]json.RawMessage
	json.Unmarshal(b, &m)
	if v, ok := m["$schema"]; ok && string(v) == "null" {
		t.Error(`emitted "$schema": null`)
	}
}

func TestPreservesUserConfig(t *testing.T) {
	d := t.TempDir()
	fp := filepath.Join(d, "frag.json")
	out := filepath.Join(d, "settings.json")
	write(t, fp, fragment)
	write(t, out, map[string]any{
		"$schema": "https://json.schemastore.org/claude-code-settings.json",
		"env":     map[string]any{"ANTHROPIC_BASE_URL": "http://localhost:9999"},
		"hooks": map[string]any{
			"PreToolUse": []any{
				map[string]any{"matcher": "Bash|bash", "hooks": []any{
					map[string]any{"type": "command", "command": "/old/providers/claude/hooks/shell-guard.sh"},
					map[string]any{"type": "command", "command": "lean-ctx hook rewrite"}}},
				map[string]any{"matcher": "Write", "hooks": []any{
					map[string]any{"type": "command", "command": "/home/u/my-audit.sh"}}},
			},
			"Notification": []any{
				map[string]any{"matcher": ".*", "hooks": []any{
					map[string]any{"type": "command", "command": "/home/u/notify.sh"}}}},
		},
		"permissions": map[string]any{"allow": []string{"mcp__custom__x"}, "deny": []string{"Bash(rm -rf /)"}},
	})
	if err := Merge(fp, out); err != nil {
		t.Fatal(err)
	}
	m := read(t, out)

	env, _ := m["env"].(map[string]any)
	if env["ANTHROPIC_BASE_URL"] != "http://localhost:9999" {
		t.Error("user env not preserved")
	}
	if !contains(eventCommands(m, "Notification"), "notify.sh") {
		t.Error("user Notification hook not preserved")
	}
	if !contains(eventCommands(m, "PreToolUse"), "my-audit.sh") {
		t.Error("user PreToolUse Write group not preserved")
	}
	if !contains(eventCommands(m, "PreToolUse"), "shell-guard.sh") {
		t.Error("our shell-guard not present")
	}
	if contains(eventCommands(m, "PreToolUse"), "/old/") {
		t.Error("stale managed group (old path) not dropped")
	}
	perms, _ := m["permissions"].(map[string]any)
	deny, _ := perms["deny"].([]any)
	if len(deny) == 0 || deny[0] != "Bash(rm -rf /)" {
		t.Error("user deny not preserved")
	}
	allow, _ := perms["allow"].([]any)
	var sawCustom, sawFrag bool
	for _, a := range allow {
		if a == "mcp__custom__x" {
			sawCustom = true
		}
		if a == "mcp__lean-ctx__ctx_read" {
			sawFrag = true
		}
	}
	if !sawCustom || !sawFrag {
		t.Errorf("allow not unioned: custom=%v frag=%v", sawCustom, sawFrag)
	}
}

func TestIdempotent(t *testing.T) {
	d := t.TempDir()
	fp := filepath.Join(d, "frag.json")
	out := filepath.Join(d, "settings.json")
	write(t, fp, fragment)
	if err := Merge(fp, out); err != nil {
		t.Fatal(err)
	}
	first, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	if err := Merge(fp, out); err != nil {
		t.Fatal(err)
	}
	second, _ := os.ReadFile(out)
	if string(first) != string(second) {
		t.Errorf("not idempotent:\nfirst:\n%s\nsecond:\n%s", first, second)
	}
	m := read(t, out)
	n := 0
	for _, c := range eventCommands(m, "PreToolUse") {
		if containsStr(c, "shell-guard.sh") {
			n++
		}
	}
	if n != 1 {
		t.Errorf("expected exactly one shell-guard, got %d", n)
	}
}
