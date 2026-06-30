package lifecycle

import (
	"os"
	"path/filepath"
	"testing"
)

func TestStatusReflectsInjectEject(t *testing.T) {
	home := t.TempDir()
	o := opts(t, home)

	// Fresh: nothing injected.
	if r := Status(o); r.Injected || r.Skills != "absent" || r.ClaudeMDLink || r.GeneratedMD || r.ManagedHooks {
		t.Errorf("fresh home should be empty: %+v", r)
	}

	// After inject: fully injected.
	if err := Inject(o); err != nil {
		t.Fatal(err)
	}
	r := Status(o)
	if !r.Injected {
		t.Errorf("after inject, Status = %+v, want Injected", r)
	}
	if r.Skills != "linked" || !r.ClaudeMDLink || !r.GeneratedMD || !r.ManagedHooks {
		t.Errorf("after inject, pieces missing: %+v", r)
	}

	// After eject: not injected again.
	if err := Eject(o); err != nil {
		t.Fatal(err)
	}
	if r := Status(o); r.Injected || r.Skills != "absent" || r.ClaudeMDLink || r.GeneratedMD {
		t.Errorf("after eject, Status = %+v, want empty", r)
	}
}

func TestStatusForeignSkillsDir(t *testing.T) {
	home := t.TempDir()
	o := opts(t, home)
	// A real (user) skills dir reads as "foreign", not "linked".
	if err := os.MkdirAll(filepath.Join(home, ".claude", "skills"), 0o755); err != nil {
		t.Fatal(err)
	}
	if r := Status(o); r.Skills != "foreign" {
		t.Errorf("real skills dir Skills = %q, want foreign", r.Skills)
	}
}
