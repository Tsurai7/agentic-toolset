package claudemd

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestStripBlockRoundTrip(t *testing.T) {
	user := "# notes\n\nhello world\n"
	withBlock := Render(user, "/x/gen.md")
	if !strings.Contains(withBlock, begin) {
		t.Fatal("Render did not add a managed block")
	}
	out, had := StripBlock(withBlock)
	if !had {
		t.Error("StripBlock did not find the block")
	}
	if strings.Contains(out, begin) || strings.Contains(out, end) {
		t.Error("managed markers remained after StripBlock")
	}
	if !strings.Contains(out, "hello world") {
		t.Errorf("user content lost: %q", out)
	}
}

func TestStripBlockOnlyBlock(t *testing.T) {
	only := Render("", "/x/gen.md")
	out, had := StripBlock(only)
	if !had || strings.TrimSpace(out) != "" {
		t.Errorf("block-only strip should be empty, got %q (had=%v)", out, had)
	}
}

func TestStripBlockNoBlock(t *testing.T) {
	out, had := StripBlock("just user text\n")
	if had || out != "just user text\n" {
		t.Errorf("no-block strip changed content: %q (had=%v)", out, had)
	}
}

func TestRemoveDeletesBlockOnlyFile(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "CLAUDE.md")
	if err := os.WriteFile(p, []byte(Render("", "/x/gen.md")), 0o644); err != nil {
		t.Fatal(err)
	}
	had, err := Remove(p)
	if err != nil || !had {
		t.Fatalf("Remove: had=%v err=%v", had, err)
	}
	if _, err := os.Stat(p); !os.IsNotExist(err) {
		t.Error("a block-only CLAUDE.md should be deleted on Remove")
	}
}

func TestRemovePreservesUserContent(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "CLAUDE.md")
	if err := os.WriteFile(p, []byte(Render("# mine\nkeep\n", "/x/gen.md")), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := Remove(p); err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(p)
	if !strings.Contains(string(b), "keep") || strings.Contains(string(b), begin) {
		t.Errorf("Remove mishandled user content: %q", string(b))
	}
}
