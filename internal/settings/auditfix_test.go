package settings

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestMergeUnreadableExistingErrors: an existing-but-unreadable settings.json is
// a hard error (not silently treated as absent and replaced with fragment-only
// content), mirroring Unmerge's non-ENOENT propagation.
func TestMergeUnreadableExistingErrors(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("unreadable-file test is meaningless as root")
	}
	dir := t.TempDir()
	frag := filepath.Join(dir, "frag.json")
	if err := os.WriteFile(frag, []byte(`{"permissions":{"allow":[]}}`), 0o644); err != nil {
		t.Fatal(err)
	}
	out := filepath.Join(dir, "settings.json")
	if err := os.WriteFile(out, []byte(`{"env":{"USER_DATA":"precious"}}`), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(out, 0o000); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(out, 0o644) })

	if err := Merge(frag, out); err == nil {
		t.Fatal("Merge over an unreadable existing file: got nil, want a read error")
	}
	_ = os.Chmod(out, 0o644)
	b, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(b), "precious") {
		t.Errorf("existing user content was clobbered: %s", b)
	}
}
