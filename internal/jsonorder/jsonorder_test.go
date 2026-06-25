package jsonorder

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestRoundTripPreservesOrder(t *testing.T) {
	in := `{"z":1,"a":{"y":2,"b":3},"m":[3,2,1]}`
	m := New()
	if err := json.Unmarshal([]byte(in), m); err != nil {
		t.Fatal(err)
	}
	if got := m.Keys(); len(got) != 3 || got[0] != "z" || got[1] != "a" || got[2] != "m" {
		t.Fatalf("key order not preserved: %v", got)
	}
	b, err := json.Marshal(m)
	if err != nil {
		t.Fatal(err)
	}
	if string(b) != in {
		t.Errorf("round-trip changed bytes:\n got %s\nwant %s", b, in)
	}
}

func TestSetAppendsAndUpdates(t *testing.T) {
	m := New()
	m.SetRaw("a", json.RawMessage("1"))
	m.SetRaw("b", json.RawMessage("2"))
	m.SetRaw("a", json.RawMessage("3")) // update keeps position
	if got := m.Keys(); len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("unexpected keys: %v", got)
	}
	if v, _ := m.GetRaw("a"); string(v) != "3" {
		t.Errorf("update failed: %s", v)
	}
}

func TestWriteFileAtomicIndented(t *testing.T) {
	d := t.TempDir()
	p := filepath.Join(d, "out.json")
	m := New()
	m.SetRaw("b", json.RawMessage(`"x"`))
	m.SetRaw("a", json.RawMessage(`"y"`))
	if err := WriteFile(p, m); err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(p)
	want := "{\n  \"b\": \"x\",\n  \"a\": \"y\"\n}\n"
	if string(b) != want {
		t.Errorf("indented output mismatch:\n got %q\nwant %q", b, want)
	}
}
