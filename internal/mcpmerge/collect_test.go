package mcpmerge

import (
	"os"
	"path/filepath"
	"testing"
)

// A fragment without an mcpServers wrapper (a typo'd key, or some other JSON)
// must be skipped, not treated as a bare server map that injects junk (BUG-16).
func TestCollectFragmentsRequiresWrapper(t *testing.T) {
	dir := t.TempDir()

	good := filepath.Join(dir, "good")
	if err := os.MkdirAll(good, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(good, "mcp.stdio.json"),
		[]byte(`{"mcpServers":{"good":{"command":"x"}}}`), 0o644); err != nil {
		t.Fatal(err)
	}

	bad := filepath.Join(dir, "bad")
	if err := os.MkdirAll(bad, 0o755); err != nil {
		t.Fatal(err)
	}
	// Typo'd wrapper key — previously its inner objects were injected as servers.
	if err := os.WriteFile(filepath.Join(bad, "mcp.json"),
		[]byte(`{"mcpServer":{"typo":{"command":"y"}}}`), 0o644); err != nil {
		t.Fatal(err)
	}

	got, err := collectFragments(dir)
	if err != nil {
		t.Fatal(err)
	}
	if !got.Has("good") {
		t.Error("valid fragment's server was not collected")
	}
	if got.Has("typo") || got.Has("mcpServer") {
		t.Errorf("malformed fragment injected junk servers: %v", got.Keys())
	}
	if len(got.Keys()) != 1 {
		t.Errorf("collected %v, want only [good]", got.Keys())
	}
}
