package jsonorder

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestWriteFilePreservesSymlink: a symlinked destination (dotfiles/stow pattern)
// must survive the atomic temp+rename — the write lands on the link target.
func TestWriteFilePreservesSymlink(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "real.json")
	if err := os.WriteFile(target, []byte("{}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(dir, "settings.json")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	m := New()
	m.SetRaw("k", json.RawMessage(`"v"`))
	if err := WriteFile(link, m); err != nil {
		t.Fatal(err)
	}
	fi, err := os.Lstat(link)
	if err != nil {
		t.Fatal(err)
	}
	if fi.Mode()&os.ModeSymlink == 0 {
		t.Fatal("destination was de-linked (replaced with a regular file)")
	}
	b, err := os.ReadFile(target)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(b), `"k"`) {
		t.Errorf("link target not updated: %s", b)
	}
}
