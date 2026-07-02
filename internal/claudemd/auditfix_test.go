package claudemd

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestEnsureUnreadableExistingErrors: an existing-but-unreadable CLAUDE.md is a
// hard error, not a silent "absent" that drops the user's prose.
func TestEnsureUnreadableExistingErrors(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("unreadable-file test is meaningless as root")
	}
	dir := t.TempDir()
	claudeMd := filepath.Join(dir, "CLAUDE.md")
	if err := os.WriteFile(claudeMd, []byte("# my prose\nremember X\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(claudeMd, 0o000); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(claudeMd, 0o644) })

	if err := Ensure(filepath.Join(dir, "gen.md"), claudeMd); err == nil {
		t.Fatal("Ensure over an unreadable existing CLAUDE.md: got nil, want a read error")
	}
	_ = os.Chmod(claudeMd, 0o644)
	b, err := os.ReadFile(claudeMd)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(b), "my prose") {
		t.Errorf("user prose was clobbered: %s", b)
	}
}

// TestAtomicWritePreservesSymlink: a symlinked destination (dotfiles pattern)
// must survive the temp+rename — the write lands on the link target.
func TestAtomicWritePreservesSymlink(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "real-CLAUDE.md")
	if err := os.WriteFile(target, []byte("old\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(dir, "CLAUDE.md")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	if err := AtomicWrite(link, []byte("new content\n"), 0o644); err != nil {
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
	if strings.TrimSpace(string(b)) != "new content" {
		t.Errorf("link target not updated: %q", b)
	}
}
