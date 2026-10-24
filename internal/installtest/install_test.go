package installtest

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func repoRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("repo root (go.mod) not found")
		}
		dir = parent
	}
}

// envWithout returns os.Environ() with HOME set and CLAUDE_CONFIG_DIR removed, so
// the installer (and any `claude` CLI it invokes) targets only the fixture HOME.
func envWithout(home string) []string {
	var out []string
	for _, kv := range os.Environ() {
		if strings.HasPrefix(kv, "HOME=") || strings.HasPrefix(kv, "CLAUDE_CONFIG_DIR=") {
			continue
		}
		out = append(out, kv)
	}
	return append(out, "HOME="+home, "DRY_RUN=0")
}

func eventCommands(settings map[string]any, event string) []string {
	var cmds []string
	hooks, _ := settings["hooks"].(map[string]any)
	groups, _ := hooks[event].([]any)
	for _, g := range groups {
		gm, _ := g.(map[string]any)
		hs, _ := gm["hooks"].([]any)
		for _, h := range hs {
			hm, _ := h.(map[string]any)
			if c, ok := hm["command"].(string); ok {
				cmds = append(cmds, c)
			}
		}
	}
	return cmds
}

func anyContains(ss []string, sub string) bool {
	for _, s := range ss {
		if strings.Contains(s, sub) {
			return true
		}
	}
	return false
}

// TestClaudeInstallPreservesUserConfig runs providers/claude/install.sh against a
// fixture HOME that already holds hand-written user config, and asserts the
// install merges in our pieces without clobbering the user's. Path-agnostic: works
// whether install.sh uses the Go binary or the Python fallback.
func TestClaudeInstallPreservesUserConfig(t *testing.T) {
	if _, err := exec.LookPath("bash"); err != nil {
		t.Skip("bash not available")
	}
	root := repoRoot(t)
	home := t.TempDir()
	cd := filepath.Join(home, ".claude")
	if err := os.MkdirAll(cd, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(cd, "CLAUDE.md"), []byte("# My notes\nkeep me\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	existing := `{"env":{"ANTHROPIC_BASE_URL":"http://localhost:9999"},` +
		`"hooks":{"Notification":[{"matcher":".*","hooks":[{"type":"command","command":"/u/notify.sh"}]}]},` +
		`"permissions":{"allow":["mcp__custom__x"],"deny":["Bash(rm -rf /)"]}}`
	if err := os.WriteFile(filepath.Join(cd, "settings.json"), []byte(existing), 0o644); err != nil {
		t.Fatal(err)
	}

	cmd := exec.Command("bash", filepath.Join(root, "providers", "claude", "install.sh"))
	cmd.Env = envWithout(home)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("install.sh failed: %v\n%s", err, out)
	}

	claudeMd, _ := os.ReadFile(filepath.Join(cd, "CLAUDE.md"))
	if !strings.Contains(string(claudeMd), "keep me") {
		t.Error("user CLAUDE.md content not preserved")
	}
	if !strings.Contains(string(claudeMd), "BEGIN agentic-cfg (managed)") {
		t.Error("CLAUDE.md missing managed @import block")
	}
	gen, err := os.ReadFile(filepath.Join(cd, "agentic-cfg.generated.md"))
	if err != nil || !strings.Contains(string(gen), "## Principles (always-on)") {
		t.Errorf("generated config missing or empty (err=%v)", err)
	}

	stRaw, err := os.ReadFile(filepath.Join(cd, "settings.json"))
	if err != nil {
		t.Fatal(err)
	}
	var st map[string]any
	if err := json.Unmarshal(stRaw, &st); err != nil {
		t.Fatalf("settings.json not valid JSON: %v", err)
	}
	if env, _ := st["env"].(map[string]any); env["ANTHROPIC_BASE_URL"] != "http://localhost:9999" {
		t.Error("user env not preserved")
	}
	if !anyContains(eventCommands(st, "Notification"), "notify.sh") {
		t.Error("user Notification hook not preserved")
	}
	if !anyContains(eventCommands(st, "PreToolUse"), "shell-guard") {
		t.Error("our shell-guard hook not registered")
	}
	perms, _ := st["permissions"].(map[string]any)
	deny, _ := perms["deny"].([]any)
	if len(deny) == 0 || deny[0] != "Bash(rm -rf /)" {
		t.Error("user deny not preserved")
	}
}

// TestClaudeInstallWeakTierDropsRedirect runs the installer with AGENTIC_TIER=weak and
// asserts the weak profile drops the lean-ctx Read/Grep redirect hook (the measured
// over-tooling driver) while keeping shell-guard and edit-lint (plans/impl-overhead/05).
func TestClaudeInstallWeakTierDropsRedirect(t *testing.T) {
	if _, err := exec.LookPath("bash"); err != nil {
		t.Skip("bash not available")
	}
	root := repoRoot(t)
	home := t.TempDir()
	if err := os.MkdirAll(filepath.Join(home, ".claude"), 0o755); err != nil {
		t.Fatal(err)
	}

	cmd := exec.Command("bash", filepath.Join(root, "providers", "claude", "install.sh"))
	cmd.Env = append(envWithout(home), "AGENTIC_TIER=weak")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("weak install.sh failed: %v\n%s", err, out)
	}

	stRaw, err := os.ReadFile(filepath.Join(home, ".claude", "settings.json"))
	if err != nil {
		t.Fatal(err)
	}
	var st map[string]any
	if err := json.Unmarshal(stRaw, &st); err != nil {
		t.Fatalf("settings.json not valid JSON: %v", err)
	}
	pre := eventCommands(st, "PreToolUse")
	if anyContains(pre, "lean-ctx hook redirect") {
		t.Error("weak tier should drop the lean-ctx redirect hook, but it is present")
	}
	if !anyContains(pre, "shell-guard") {
		t.Error("weak tier must keep shell-guard")
	}
	if !anyContains(eventCommands(st, "PostToolUse"), "edit-lint") {
		t.Error("weak tier must keep edit-lint")
	}
}
