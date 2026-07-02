package main

import "testing"

// TestIsSandboxHome pins the C5 rule: the global `claude` MCP step is skipped
// when --home targets anything other than the user's real home.
func TestIsSandboxHome(t *testing.T) {
	cases := []struct {
		name     string
		resolved string
		real     string
		realErr  error
		want     bool
	}{
		{"sandbox differs", "/tmp/sandbox", "/Users/me", nil, true},
		{"same home", "/Users/me", "/Users/me", nil, false},
		{"same home trailing slash", "/Users/me/", "/Users/me", nil, false},
		{"real home unresolvable", "/tmp/sandbox", "", errFake, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := isSandboxHome(c.resolved, c.real, c.realErr); got != c.want {
				t.Errorf("isSandboxHome(%q,%q,%v) = %v, want %v", c.resolved, c.real, c.realErr, got, c.want)
			}
		})
	}
}

var errFake = &fakeErr{}

type fakeErr struct{}

func (*fakeErr) Error() string { return "cannot resolve home" }
