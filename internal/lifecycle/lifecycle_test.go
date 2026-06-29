package lifecycle

import (
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// repoRoot returns the agentic-cfg repo root, derived from this test file's path
// (<root>/internal/lifecycle/lifecycle_test.go).
func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Dir(filepath.Dir(filepath.Dir(file)))
}

func opts(t *testing.T, home string) Options {
	return Options{Root: repoRoot(t), Home: home, SkipMCP: true, Log: io.Discard}
}

func readFile(t *testing.T, p string) string {
	t.Helper()
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatalf("read %s: %v", p, err)
	}
	return string(b)
}

// userSettings is a settings.json a user might already have: a local env, their
// own hook, their own allow entry, and a deny entry. None of it is ours.
const userSettings = `{
  "env": {"ANTHROPIC_BASE_URL": "http://localhost:1234"},
  "hooks": {
    "PreToolUse": [
      {"matcher": "MyTool", "hooks": [{"type": "command", "command": "/usr/local/bin/my-user-hook.sh"}]}
    ]
  },
  "permissions": {"allow": ["Bash(mycmd:*)"], "deny": ["Bash(rm:*)"]}
}`

func TestInjectThenEjectRoundTrip(t *testing.T) {
	home := t.TempDir()
	cd := filepath.Join(home, ".claude")
	if err := os.MkdirAll(cd, 0o755); err != nil {
		t.Fatal(err)
	}
	// Seed hand-written user content that must survive both operations.
	if err := os.WriteFile(filepath.Join(cd, "CLAUDE.md"), []byte("# My personal notes\n\nremember the milk\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(cd, "settings.json"), []byte(userSettings), 0o644); err != nil {
		t.Fatal(err)
	}

	// ---- inject ----
	if err := Inject(opts(t, home)); err != nil {
		t.Fatalf("Inject: %v", err)
	}

	// skills symlink points at our source
	link, err := os.Readlink(filepath.Join(cd, "skills"))
	if err != nil || link != filepath.Join(repoRoot(t), "core", "skills") {
		t.Errorf("skills symlink = %q, %v", link, err)
	}
	// generated md exists with resolved content
	gen := readFile(t, filepath.Join(cd, generatedName))
	if strings.Contains(gen, "__AGENTIC_ROOT__") {
		t.Error("generated md still has unresolved __AGENTIC_ROOT__")
	}
	if !strings.Contains(gen, "Agent instructions") || !strings.Contains(gen, "Principles (always-on)") {
		t.Error("generated md missing AGENTS.md / principles content")
	}
	// CLAUDE.md: managed block added AND user content preserved
	claudeMd := readFile(t, filepath.Join(cd, "CLAUDE.md"))
	if !strings.Contains(claudeMd, "BEGIN agentic-cfg (managed)") || !strings.Contains(claudeMd, "@"+filepath.Join(cd, generatedName)) {
		t.Error("CLAUDE.md missing managed @import block")
	}
	if !strings.Contains(claudeMd, "remember the milk") {
		t.Error("inject clobbered user CLAUDE.md content")
	}
	// settings.json: managed hooks + allow present; user content preserved
	s := parseJSON(t, filepath.Join(cd, "settings.json"))
	if !settingsContains(t, filepath.Join(cd, "settings.json"), "shell-guard.sh") {
		t.Error("settings missing managed shell-guard hook after inject")
	}
	allow := allowList(t, s)
	if !contains(allow, "mcp__lean-ctx__ctx_read") || !contains(allow, "Bash(mycmd:*)") {
		t.Errorf("allow after inject = %v (want managed + user entries)", allow)
	}
	if env := s["env"].(map[string]any); env["ANTHROPIC_BASE_URL"] != "http://localhost:1234" {
		t.Error("inject lost user env")
	}
	if !settingsContains(t, filepath.Join(cd, "settings.json"), "my-user-hook.sh") {
		t.Error("inject lost user hook")
	}

	// ---- eject ----
	if err := Eject(opts(t, home)); err != nil {
		t.Fatalf("Eject: %v", err)
	}

	if _, err := os.Lstat(filepath.Join(cd, "skills")); !os.IsNotExist(err) {
		t.Error("eject left the skills symlink behind")
	}
	if _, err := os.Stat(filepath.Join(cd, generatedName)); !os.IsNotExist(err) {
		t.Error("eject left the generated md behind")
	}
	claudeMd = readFile(t, filepath.Join(cd, "CLAUDE.md"))
	if strings.Contains(claudeMd, "BEGIN agentic-cfg (managed)") {
		t.Error("eject left the managed CLAUDE.md block behind")
	}
	if !strings.Contains(claudeMd, "remember the milk") {
		t.Error("eject destroyed user CLAUDE.md content")
	}
	if settingsContains(t, filepath.Join(cd, "settings.json"), "shell-guard.sh") {
		t.Error("eject left a managed hook behind")
	}
	if !settingsContains(t, filepath.Join(cd, "settings.json"), "my-user-hook.sh") {
		t.Error("eject destroyed the user hook")
	}
	s = parseJSON(t, filepath.Join(cd, "settings.json"))
	allow = allowList(t, s)
	if contains(allow, "mcp__lean-ctx__ctx_read") {
		t.Error("eject left a managed allow entry behind")
	}
	if !contains(allow, "Bash(mycmd:*)") {
		t.Errorf("eject removed the user allow entry; allow = %v", allow)
	}
	if env := s["env"].(map[string]any); env["ANTHROPIC_BASE_URL"] != "http://localhost:1234" {
		t.Error("eject lost user env")
	}
}

func TestInjectIdempotent(t *testing.T) {
	home := t.TempDir()
	o := opts(t, home)
	for i := 0; i < 2; i++ {
		if err := Inject(o); err != nil {
			t.Fatalf("Inject #%d: %v", i, err)
		}
	}
	cd := filepath.Join(home, ".claude")
	claudeMd := readFile(t, filepath.Join(cd, "CLAUDE.md"))
	if n := strings.Count(claudeMd, "BEGIN agentic-cfg (managed)"); n != 1 {
		t.Errorf("expected exactly one managed block after double inject, got %d", n)
	}
	// allow entries must not duplicate
	s := parseJSON(t, filepath.Join(cd, "settings.json"))
	allow := allowList(t, s)
	seen := map[string]bool{}
	for _, a := range allow {
		if seen[a] {
			t.Errorf("duplicate allow entry %q after double inject", a)
		}
		seen[a] = true
	}
}

func TestEjectWithNothingInjected(t *testing.T) {
	home := t.TempDir()
	if err := Eject(opts(t, home)); err != nil {
		t.Fatalf("Eject on a clean home should be a no-op, got: %v", err)
	}
}

func TestInjectPreservesRealSkillsDir(t *testing.T) {
	home := t.TempDir()
	cd := filepath.Join(home, ".claude")
	userSkill := filepath.Join(cd, "skills", "my-skill")
	if err := os.MkdirAll(userSkill, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(userSkill, "SKILL.md"), []byte("mine"), 0o644); err != nil {
		t.Fatal(err)
	}

	if err := Inject(opts(t, home)); err != nil {
		t.Fatalf("Inject: %v", err)
	}
	// skills is now our symlink; the user's real dir was backed up, not destroyed.
	if fi, err := os.Lstat(filepath.Join(cd, "skills")); err != nil || fi.Mode()&os.ModeSymlink == 0 {
		t.Errorf("skills should be a symlink after inject: %v", err)
	}
	if got := readFile(t, filepath.Join(cd, skillsBackup, "my-skill", "SKILL.md")); got != "mine" {
		t.Errorf("user skill not backed up intact, got %q", got)
	}

	// eject restores the user's real dir
	if err := Eject(opts(t, home)); err != nil {
		t.Fatalf("Eject: %v", err)
	}
	if got := readFile(t, filepath.Join(cd, "skills", "my-skill", "SKILL.md")); got != "mine" {
		t.Errorf("user skill not restored after eject, got %q", got)
	}
}

func TestDryRunChangesNothing(t *testing.T) {
	home := t.TempDir()
	o := opts(t, home)
	o.DryRun = true
	if err := Inject(o); err != nil {
		t.Fatalf("dry-run Inject: %v", err)
	}
	if entries, _ := os.ReadDir(filepath.Join(home, ".claude")); len(entries) != 0 {
		t.Errorf("dry-run inject wrote files: %v", entries)
	}
}

func TestGeneratedMD(t *testing.T) {
	md, err := GeneratedMD(repoRoot(t))
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"Agent instructions", "Principles (always-on)", "User rules"} {
		if !strings.Contains(md, want) {
			t.Errorf("generated md missing %q", want)
		}
	}
	if strings.Contains(md, "__AGENTIC_ROOT__") {
		t.Error("generated md left an unresolved placeholder")
	}
}

// ---- helpers ----

func parseJSON(t *testing.T, path string) map[string]any {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal([]byte(readFile(t, path)), &m); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
	return m
}

func settingsContains(t *testing.T, path, substr string) bool {
	t.Helper()
	return strings.Contains(readFile(t, path), substr)
}

func allowList(t *testing.T, s map[string]any) []string {
	t.Helper()
	perms, ok := s["permissions"].(map[string]any)
	if !ok {
		return nil
	}
	raw, ok := perms["allow"].([]any)
	if !ok {
		return nil
	}
	out := make([]string, 0, len(raw))
	for _, v := range raw {
		out = append(out, v.(string))
	}
	return out
}

func contains(ss []string, want string) bool {
	for _, s := range ss {
		if s == want {
			return true
		}
	}
	return false
}
