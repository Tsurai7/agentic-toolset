package lifecycle

import (
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func lcRepoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Dir(filepath.Dir(filepath.Dir(file)))
}

// TestGeneratedMDNoDoubleBlankBeforeHeaders pins the GeneratedMD parity fix: the
// Go-generated file uses exactly one blank line before each managed section
// header (matching install.sh's `echo ""`), so the two documented install entry
// points don't rewrite the file on every alternation.
func TestGeneratedMDNoDoubleBlankBeforeHeaders(t *testing.T) {
	out, err := GeneratedMD(lcRepoRoot(t))
	if err != nil {
		t.Fatal(err)
	}
	for _, h := range []string{"## Principles (always-on)", "## User rules"} {
		if strings.Contains(out, "\n\n\n"+h) {
			t.Errorf("double blank line before %q (should be a single blank line)", h)
		}
		if !strings.Contains(out, "\n\n"+h) {
			t.Errorf("expected exactly one blank line before %q", h)
		}
	}
}
