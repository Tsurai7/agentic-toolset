package settings

import (
	"bytes"
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

// groupsContaining counts hooks[event] groups that have at least one command
// containing sub — used to assert de-duplication down to one group per matcher.
func groupsContaining(m map[string]any, event, sub string) int {
	n := 0
	hooks, _ := m["hooks"].(map[string]any)
	groups, _ := hooks[event].([]any)
	for _, g := range groups {
		gm, _ := g.(map[string]any)
		hs, _ := gm["hooks"].([]any)
		for _, h := range hs {
			hm, _ := h.(map[string]any)
			if c, ok := hm["command"].(string); ok && containsStr(c, sub) {
				n++
				break
			}
		}
	}
	return n
}

func contains(ss []string, sub string) bool {
	for _, s := range ss {
		if s == sub || (sub != "" && len(s) >= len(sub) && containsStr(s, sub)) {
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
				map[string]any{"type": "command", "command": "ROOT/providers/claude/hooks/shell-guard.sh"},
			}},
			map[string]any{"matcher": "Read", "hooks": []any{
				map[string]any{"type": "command", "command": "lean-ctx hook redirect"},
			}},
		},
		"Stop": []any{
			map[string]any{"matcher": ".*", "hooks": []any{
				map[string]any{"type": "command", "command": "lean-ctx hook observe"},
			}},
		},
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
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatalf("output is not valid JSON: %v", err)
	}
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
					map[string]any{"type": "command", "command": "lean-ctx hook rewrite"},
				}},
				map[string]any{"matcher": "Write", "hooks": []any{
					map[string]any{"type": "command", "command": "/home/u/my-audit.sh"},
				}},
			},
			"Notification": []any{
				map[string]any{"matcher": ".*", "hooks": []any{
					map[string]any{"type": "command", "command": "/home/u/notify.sh"},
				}},
			},
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
	if !bytes.Equal(first, second) {
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

// TestAbsolutePathLeanCtxDeduped reproduces the live ~/.claude/settings.json bug:
// a standalone absolute-path `lean-ctx hook rewrite` group (no literal "lean-ctx
// hook " prefix) must still be recognized as managed and replaced, not kept
// alongside the fragment's own Read-matcher group.
func TestAbsolutePathLeanCtxDeduped(t *testing.T) {
	d := t.TempDir()
	fp := filepath.Join(d, "frag.json")
	out := filepath.Join(d, "settings.json")
	write(t, fp, fragment)
	write(t, out, map[string]any{
		"hooks": map[string]any{
			"PreToolUse": []any{
				map[string]any{"matcher": "Read", "hooks": []any{
					map[string]any{"type": "command", "command": "/opt/homebrew/bin/lean-ctx hook rewrite"},
				}},
			},
		},
	})
	if err := Merge(fp, out); err != nil {
		t.Fatal(err)
	}
	m := read(t, out)
	if contains(eventCommands(m, "PreToolUse"), "/opt/homebrew/bin/lean-ctx") {
		t.Error("absolute-path lean-ctx group not recognized as managed; stale group survived")
	}
	if n := groupsContaining(m, "PreToolUse", "lean-ctx hook"); n != 1 {
		t.Errorf("expected exactly one lean-ctx hook group after merge, got %d", n)
	}
}

// TestDuplicateShellGuardDeduped simulates today's live duplicate state: two
// shell-guard groups already present before the fragment is merged in. Merge
// must collapse them to exactly one (the fragment's), not three.
func TestDuplicateShellGuardDeduped(t *testing.T) {
	d := t.TempDir()
	fp := filepath.Join(d, "frag.json")
	out := filepath.Join(d, "settings.json")
	write(t, fp, fragment)
	write(t, out, map[string]any{
		"hooks": map[string]any{
			"PreToolUse": []any{
				map[string]any{"matcher": "Bash|bash", "hooks": []any{
					map[string]any{"type": "command", "command": "/opt/homebrew/lean-ctx/providers/claude/hooks/shell-guard.sh"},
				}},
				map[string]any{"matcher": "Bash|bash", "hooks": []any{
					map[string]any{"type": "command", "command": "/old/clone/providers/claude/hooks/shell-guard.sh"},
				}},
			},
		},
	})
	if err := Merge(fp, out); err != nil {
		t.Fatal(err)
	}
	m := read(t, out)
	if n := groupsContaining(m, "PreToolUse", "shell-guard.sh"); n != 1 {
		t.Errorf("expected exactly one shell-guard group after dedup, got %d", n)
	}
}

// TestUserOwnedHookSurvives ensures a genuinely user-owned hook — one that does
// not match any managed shape — is never touched by the basename recognition.
func TestUserOwnedHookSurvives(t *testing.T) {
	d := t.TempDir()
	fp := filepath.Join(d, "frag.json")
	out := filepath.Join(d, "settings.json")
	write(t, fp, fragment)
	write(t, out, map[string]any{
		"hooks": map[string]any{
			"PreToolUse": []any{
				map[string]any{"matcher": "Bash|bash", "hooks": []any{
					map[string]any{"type": "command", "command": "/home/u/bin/my-custom-hook.sh"},
				}},
			},
		},
	})
	if err := Merge(fp, out); err != nil {
		t.Fatal(err)
	}
	m := read(t, out)
	if !contains(eventCommands(m, "PreToolUse"), "my-custom-hook.sh") {
		t.Error("user-owned hook was dropped by Merge")
	}
	if n := groupsContaining(m, "PreToolUse", "my-custom-hook.sh"); n != 1 {
		t.Errorf("expected the user-owned group to survive exactly once, got %d", n)
	}
}

// TestMergeDropsManagedAllowAbsentFromFragment is the weak-tier proof at the
// settings-package level (plan 06 change 3): a fragment whose permissions.allow
// no longer lists the managed mcp__lean-ctx__* entries must cause Merge to
// REMOVE those entries from the existing settings, not just skip adding new
// ones — while a user-added allow entry outside the managed prefix survives
// byte-identical.
func TestMergeDropsManagedAllowAbsentFromFragment(t *testing.T) {
	d := t.TempDir()
	fp := filepath.Join(d, "frag.json")
	out := filepath.Join(d, "settings.json")
	// Weak-tier fragment: still declares "permissions" but with an empty allow.
	write(t, fp, map[string]any{
		"hooks":       map[string]any{"PreToolUse": []any{}},
		"permissions": map[string]any{"allow": []string{}},
	})
	write(t, out, map[string]any{
		"permissions": map[string]any{
			"allow": []string{
				"mcp__lean-ctx__ctx_read", "mcp__lean-ctx__ctx_search", "mcp__lean-ctx__ctx_tree",
				"mcp__lean-ctx__ctx_overview", "mcp__lean-ctx__ctx_plan", "mcp__lean-ctx__ctx_metrics",
				"mcp__lean-ctx__ctx_compress", "mcp__lean-ctx__ctx_session", "mcp__lean-ctx__ctx_knowledge",
				"mcp__lean-ctx__ctx_graph", "mcp__lean-ctx__ctx_retrieve", "mcp__lean-ctx__ctx_provider",
				"Bash(mycmd:*)",
			},
			"deny": []string{"Bash(rm -rf /)"},
		},
	})
	if err := Merge(fp, out); err != nil {
		t.Fatal(err)
	}
	m := read(t, out)
	perms, _ := m["permissions"].(map[string]any)
	allow, _ := perms["allow"].([]any)
	if len(allow) != 1 || allow[0] != "Bash(mycmd:*)" {
		t.Errorf("expected only the user-added entry to survive, got %v", allow)
	}
	deny, _ := perms["deny"].([]any)
	if len(deny) == 0 || deny[0] != "Bash(rm -rf /)" {
		t.Error("user deny not preserved")
	}
}

// TestMergeFragmentWithoutPermissionsLeavesManagedSetAlone: a fragment that
// omits "permissions" entirely expresses no opinion and must not wipe the
// managed allow set (distinct from a fragment that declares permissions with
// an empty allow, which does drop it — see
// TestMergeDropsManagedAllowAbsentFromFragment).
func TestMergeFragmentWithoutPermissionsLeavesManagedSetAlone(t *testing.T) {
	d := t.TempDir()
	fp := filepath.Join(d, "frag.json")
	out := filepath.Join(d, "settings.json")
	write(t, fp, map[string]any{"hooks": map[string]any{"PreToolUse": []any{}}})
	write(t, out, map[string]any{
		"permissions": map[string]any{"allow": []string{"mcp__lean-ctx__ctx_read"}},
	})
	if err := Merge(fp, out); err != nil {
		t.Fatal(err)
	}
	m := read(t, out)
	perms, _ := m["permissions"].(map[string]any)
	allow, _ := perms["allow"].([]any)
	if len(allow) != 1 || allow[0] != "mcp__lean-ctx__ctx_read" {
		t.Errorf("fragment without permissions must not alter the managed set, got %v", allow)
	}
}

// TestUnmergeRemovesPathQualifiedGroups checks the inverse path: Unmerge/eject
// must also recognize and remove path-qualified managed groups (absolute-path
// lean-ctx and moved-clone providers/claude/hooks/ commands), not just the
// literal-prefix ones.
func TestUnmergeRemovesPathQualifiedGroups(t *testing.T) {
	d := t.TempDir()
	fp := filepath.Join(d, "frag.json")
	out := filepath.Join(d, "settings.json")
	write(t, fp, fragment)
	write(t, out, map[string]any{
		"hooks": map[string]any{
			"PreToolUse": []any{
				map[string]any{"matcher": "Bash|bash", "hooks": []any{
					map[string]any{"type": "command", "command": "/old/clone/providers/claude/hooks/shell-guard.sh"},
				}},
				map[string]any{"matcher": "Read", "hooks": []any{
					map[string]any{"type": "command", "command": "/opt/homebrew/bin/lean-ctx hook rewrite"},
				}},
				map[string]any{"matcher": "Write", "hooks": []any{
					map[string]any{"type": "command", "command": "/home/u/my-audit.sh"},
				}},
			},
		},
	})
	if err := Unmerge(fp, out); err != nil {
		t.Fatal(err)
	}
	m := read(t, out)
	cmds := eventCommands(m, "PreToolUse")
	if contains(cmds, "shell-guard.sh") {
		t.Error("Unmerge left a path-qualified shell-guard group in place")
	}
	if contains(cmds, "lean-ctx hook rewrite") {
		t.Error("Unmerge left an absolute-path lean-ctx hook group in place")
	}
	if !contains(cmds, "my-audit.sh") {
		t.Error("Unmerge removed a user-owned group")
	}
}
