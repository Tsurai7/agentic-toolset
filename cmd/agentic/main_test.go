package main

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

// repoRoot derives the repo root from this test file (cmd/agentic/main_test.go).
func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Dir(filepath.Dir(filepath.Dir(file)))
}

// TestRunInjectEject exercises the actual CLI command path used by both
// `agentic inject|eject` and `agentic-cfg inject|eject` (the bin/agentic-cfg
// wrapper just execs this binary), against a temp HOME with MCP skipped.
func TestRunInjectEject(t *testing.T) {
	root := repoRoot(t)
	home := t.TempDir()
	cd := filepath.Join(home, ".claude")

	if code := run([]string{"inject", "--root", root, "--home", home, "--skip-mcp"}); code != 0 {
		t.Fatalf("inject exit = %d, want 0", code)
	}
	if _, err := os.Lstat(filepath.Join(cd, "skills")); err != nil {
		t.Errorf("inject did not create the skills symlink: %v", err)
	}
	if _, err := os.Stat(filepath.Join(cd, "CLAUDE.md")); err != nil {
		t.Errorf("inject did not create CLAUDE.md: %v", err)
	}
	if _, err := os.Stat(filepath.Join(cd, "settings.json")); err != nil {
		t.Errorf("inject did not create settings.json: %v", err)
	}

	if code := run([]string{"eject", "--root", root, "--home", home, "--skip-mcp"}); code != 0 {
		t.Fatalf("eject exit = %d, want 0", code)
	}
	if _, err := os.Lstat(filepath.Join(cd, "skills")); !os.IsNotExist(err) {
		t.Error("eject left the skills symlink behind")
	}
	if _, err := os.Stat(filepath.Join(cd, "agentic-cfg.generated.md")); !os.IsNotExist(err) {
		t.Error("eject left the generated md behind")
	}
}

func TestRunStatus(t *testing.T) {
	root := repoRoot(t)
	home := t.TempDir()
	// Not injected -> exit 1.
	if code := run([]string{"status", "--root", root, "--home", home}); code != 1 {
		t.Errorf("status on fresh home exit = %d, want 1", code)
	}
	if code := run([]string{"inject", "--root", root, "--home", home, "--skip-mcp"}); code != 0 {
		t.Fatalf("inject exit = %d", code)
	}
	// Injected -> exit 0.
	if code := run([]string{"status", "--root", root, "--home", home, "--json"}); code != 0 {
		t.Errorf("status after inject exit = %d, want 0", code)
	}
}

func TestLinkInto(t *testing.T) {
	dir := t.TempDir()
	exe := filepath.Join(t.TempDir(), "agentic")
	if err := os.WriteFile(exe, []byte("#!/bin/sh\n"), 0o755); err != nil {
		t.Fatal(err)
	}

	created, skipped, err := linkInto(exe, dir, []string{"agentic", "agentic-cfg"})
	if err != nil || len(created) != 2 || len(skipped) != 0 {
		t.Fatalf("linkInto: created=%v skipped=%v err=%v", created, skipped, err)
	}
	for _, name := range []string{"agentic", "agentic-cfg"} {
		if dest, _ := os.Readlink(filepath.Join(dir, name)); dest != exe {
			t.Errorf("%s -> %s, want %s", name, dest, exe)
		}
	}

	// Idempotent: re-linking is fine and leaves the correct symlink.
	if c, _, err := linkInto(exe, dir, []string{"agentic"}); err != nil || len(c) != 1 {
		t.Errorf("re-link not idempotent: %v %v", c, err)
	}

	// A real (non-symlink) file is skipped, never clobbered.
	real := filepath.Join(dir, "realfile")
	if err := os.WriteFile(real, []byte("keep"), 0o644); err != nil {
		t.Fatal(err)
	}
	_, skip, _ := linkInto(exe, dir, []string{"realfile"})
	if len(skip) != 1 {
		t.Errorf("a real file should be skipped, got skipped=%v", skip)
	}
	if b, _ := os.ReadFile(real); string(b) != "keep" {
		t.Error("linkInto clobbered a real file")
	}
}

func TestRunDispatchErrors(t *testing.T) {
	if code := run([]string{"bogus-subcommand"}); code != 2 {
		t.Errorf("unknown command exit = %d, want 2", code)
	}
	if code := run(nil); code != 2 {
		t.Errorf("no-args exit = %d, want 2", code)
	}
	if code := run([]string{"--help"}); code != 0 {
		t.Errorf("--help exit = %d, want 0", code)
	}
}
