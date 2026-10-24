package mcpmerge

import "testing"

func TestSubstituteSinglePass(t *testing.T) {
	env := map[string]string{
		"A":                 "__B__", // a value that itself looks like a placeholder
		"B":                 "x",
		"NPX":               "/opt/npx",
		"LEAN_CTX":          "/lc",
		"LEAN_CTX_DATA_DIR": "/lc/data",
	}

	// Single pass: __A__ -> literal "__B__", NOT re-substituted to "x".
	if got := substitute("__A__", env).(string); got != "__B__" {
		t.Errorf("substitute(__A__) = %q, want __B__ (no double-substitution)", got)
	}
	// A key that is a prefix of another must not clobber the longer one.
	if got := substitute("__LEAN_CTX_DATA_DIR__", env).(string); got != "/lc/data" {
		t.Errorf("substitute(__LEAN_CTX_DATA_DIR__) = %q, want /lc/data", got)
	}
	if got := substitute("__LEAN_CTX__", env).(string); got != "/lc" {
		t.Errorf("substitute(__LEAN_CTX__) = %q, want /lc", got)
	}
	// Unknown placeholder is left untouched.
	if got := substitute("__UNKNOWN__", env).(string); got != "__UNKNOWN__" {
		t.Errorf("substitute(__UNKNOWN__) = %q, want untouched", got)
	}
	// Recurses into maps and slices.
	out := substitute(map[string]any{"command": "__NPX__", "args": []any{"-y", "__NPX__"}}, env).(map[string]any)
	if out["command"] != "/opt/npx" {
		t.Errorf("nested command = %v", out["command"])
	}
	if out["args"].([]any)[1] != "/opt/npx" {
		t.Errorf("nested arg = %v", out["args"])
	}
}
