package claudemd

import "strings"

import "testing"

func TestFreshFile(t *testing.T) {
	got := Render("", "/home/u/.claude/agentic-cfg.generated.md")
	if !strings.Contains(got, begin) || !strings.Contains(got, "@/home/u/.claude/agentic-cfg.generated.md") {
		t.Errorf("fresh render missing block/import:\n%s", got)
	}
}

func TestPreservesUserContent(t *testing.T) {
	existing := "# My notes\nremember X\n"
	got := Render(existing, "/gen.md")
	if !strings.Contains(got, "My notes") || !strings.Contains(got, "remember X") {
		t.Error("user content not preserved")
	}
	if !strings.Contains(got, begin) {
		t.Error("managed block not appended")
	}
}

func TestLegacyMigration(t *testing.T) {
	legacy := legacySignature + " — do not edit -->\n\nbig inline\n## Principles (always-on)\nLEGACY_MARKER\n"
	got := Render(legacy, "/gen.md")
	if strings.Contains(got, "LEGACY_MARKER") {
		t.Error("legacy inline content not removed")
	}
	if !strings.Contains(got, begin) {
		t.Error("managed block missing after migration")
	}
}

func TestIdempotent(t *testing.T) {
	first := Render("# notes\n", "/gen.md")
	second := Render(first, "/gen.md")
	if first != second {
		t.Errorf("not idempotent:\nfirst:\n%s\nsecond:\n%s", first, second)
	}
	if strings.Count(second, begin) != 1 {
		t.Errorf("expected exactly one managed block, got %d", strings.Count(second, begin))
	}
}
