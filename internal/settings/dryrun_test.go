package settings

import (
	"os"
	"path/filepath"
	"testing"
)

// Under DRY_RUN=1, Merge must preview (print) and NOT create or modify the file.
func TestMergeDryRunDoesNotWrite(t *testing.T) {
	t.Setenv("DRY_RUN", "1")
	dir := t.TempDir()
	frag := filepath.Join(dir, "frag.json")
	if err := os.WriteFile(frag, []byte(`{"permissions":{"allow":["mcp__x__y"]}}`), 0o644); err != nil {
		t.Fatal(err)
	}
	out := filepath.Join(dir, "settings.json") // does not exist
	if err := Merge(frag, out); err != nil {
		t.Fatalf("Merge dry-run: %v", err)
	}
	if _, err := os.Stat(out); !os.IsNotExist(err) {
		t.Error("DRY_RUN Merge wrote the output file; it must only preview")
	}
}
