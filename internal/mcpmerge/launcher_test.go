package mcpmerge

import "testing"

func TestUnresolvedLauncherWarning(t *testing.T) {
	cases := []struct {
		name     string
		val      string
		found    bool
		wantWarn bool
	}{
		{"bare fallback, not on PATH", "npx", false, true},
		{"empty, not on PATH", "", false, true},
		{"resolved on PATH", "npx", true, false},
		{"explicit env path, not on PATH", "/opt/homebrew/bin/npx", false, false},
		{"explicit env path, on PATH", "/opt/homebrew/bin/npx", true, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := unresolvedLauncherWarning(c.val, c.found)
			if (got != "") != c.wantWarn {
				t.Errorf("unresolvedLauncherWarning(%q, %v) = %q, wantWarn=%v", c.val, c.found, got, c.wantWarn)
			}
		})
	}
}
