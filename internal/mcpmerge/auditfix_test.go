package mcpmerge

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func mcpRepoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Dir(filepath.Dir(filepath.Dir(file)))
}

// TestMergeCursorUnreadableExistingErrors: an existing-but-unreadable mcp.json is
// a hard error, not a silent "absent" that drops the user's hand-added servers.
func TestMergeCursorUnreadableExistingErrors(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("unreadable-file test is meaningless as root")
	}
	root := mcpRepoRoot(t)
	dir := t.TempDir()
	out := filepath.Join(dir, "mcp.json")
	if err := os.WriteFile(out, []byte(`{"mcpServers":{"mine":{"command":"x"}}}`), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(out, 0o000); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(out, 0o644) })

	if err := MergeCursor(root, out); err == nil {
		t.Fatal("MergeCursor over an unreadable existing file: got nil, want a read error")
	}
	_ = os.Chmod(out, 0o644)
	b, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(b), "mine") {
		t.Errorf("user server was clobbered: %s", b)
	}
}
