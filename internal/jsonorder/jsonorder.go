// Package jsonorder provides a JSON object type that preserves key order across
// Unmarshal/Marshal. The Python install scripts write json.dumps(...) without
// sort_keys, so the output follows insertion order; Go's default map marshaling
// sorts keys, which would reorder hand-added entries (e.g. MCP servers, settings
// keys) and produce noisy diffs and misleading backups. Map keeps order stable.
package jsonorder

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// Map is an order-preserving JSON object. Values are kept as raw JSON, so nested
// objects and arrays retain their original key/element order verbatim.
type Map struct {
	keys   []string
	values map[string]json.RawMessage
}

// New returns an empty Map.
func New() *Map {
	return &Map{values: map[string]json.RawMessage{}}
}

// Keys returns the keys in order.
func (m *Map) Keys() []string { return m.keys }

// Has reports whether key k is present.
func (m *Map) Has(k string) bool {
	_, ok := m.values[k]
	return ok
}

// GetRaw returns the raw JSON value for k.
func (m *Map) GetRaw(k string) (json.RawMessage, bool) {
	v, ok := m.values[k]
	return v, ok
}

// SetRaw sets k to a raw JSON value, appending k if new (preserving order).
func (m *Map) SetRaw(k string, raw json.RawMessage) {
	if m.values == nil {
		m.values = map[string]json.RawMessage{}
	}
	if _, ok := m.values[k]; !ok {
		m.keys = append(m.keys, k)
	}
	m.values[k] = raw
}

// Set marshals v and sets it at k.
func (m *Map) Set(k string, v any) error {
	b, err := json.Marshal(v)
	if err != nil {
		return err
	}
	m.SetRaw(k, b)
	return nil
}

// Get unmarshals the value at k into out. Returns false if k is absent.
func (m *Map) Get(k string, out any) (bool, error) {
	v, ok := m.values[k]
	if !ok {
		return false, nil
	}
	return true, json.Unmarshal(v, out)
}

// Delete removes k, preserving the order of the rest.
func (m *Map) Delete(k string) {
	if _, ok := m.values[k]; !ok {
		return
	}
	delete(m.values, k)
	for i, kk := range m.keys {
		if kk == k {
			m.keys = append(m.keys[:i], m.keys[i+1:]...)
			break
		}
	}
}

// Clone returns a deep copy.
func (m *Map) Clone() *Map {
	c := &Map{
		keys:   make([]string, len(m.keys)),
		values: make(map[string]json.RawMessage, len(m.values)),
	}
	copy(c.keys, m.keys)
	for k, v := range m.values {
		vc := make(json.RawMessage, len(v))
		copy(vc, v)
		c.values[k] = vc
	}
	return c
}

// UnmarshalJSON parses a JSON object, preserving key order. A JSON null is
// treated as an empty object.
func (m *Map) UnmarshalJSON(b []byte) error {
	m.keys = nil
	m.values = map[string]json.RawMessage{}
	if bytes.Equal(bytes.TrimSpace(b), []byte("null")) {
		return nil
	}
	dec := json.NewDecoder(bytes.NewReader(b))
	t, err := dec.Token()
	if err != nil {
		return err
	}
	if d, ok := t.(json.Delim); !ok || d != '{' {
		return fmt.Errorf("jsonorder: expected JSON object, got %v", t)
	}
	for dec.More() {
		kt, err := dec.Token()
		if err != nil {
			return err
		}
		key, ok := kt.(string)
		if !ok {
			return fmt.Errorf("jsonorder: expected string key, got %v", kt)
		}
		var raw json.RawMessage
		if err := dec.Decode(&raw); err != nil {
			return err
		}
		if _, seen := m.values[key]; !seen {
			m.keys = append(m.keys, key)
		}
		m.values[key] = raw
	}
	_, err = dec.Token() // consume closing '}'
	return err
}

// MarshalJSON writes the object with keys in order (compact).
func (m *Map) MarshalJSON() ([]byte, error) {
	var buf bytes.Buffer
	buf.WriteByte('{')
	for i, k := range m.keys {
		if i > 0 {
			buf.WriteByte(',')
		}
		kb, err := json.Marshal(k)
		if err != nil {
			return nil, err
		}
		buf.Write(kb)
		buf.WriteByte(':')
		buf.Write(m.values[k])
	}
	buf.WriteByte('}')
	return buf.Bytes(), nil
}

// ReadFile parses a JSON object file into a Map.
func ReadFile(path string) (*Map, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	m := New()
	if err := json.Unmarshal(b, m); err != nil {
		return nil, err
	}
	return m, nil
}

// Marshal returns m as indented JSON (2 spaces, no HTML escaping, trailing
// newline) — the exact bytes WriteFile persists. Useful for previewing a
// would-be write (e.g. a --dry-run) without touching the filesystem.
func Marshal(m *Map) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(m); err != nil { // Encode appends a trailing newline
		return nil, err
	}
	return buf.Bytes(), nil
}

// WriteFile writes m as indented JSON (2 spaces, no HTML escaping, trailing
// newline) atomically via a temp file + fsync + rename, preserving the target's
// prior file mode (or 0644 for a newly-created file) so a merge never silently
// chmods the user's live config to the temp file's restrictive 0600 default.
func WriteFile(path string, m *Map) error {
	data, err := Marshal(m)
	if err != nil {
		return err
	}
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	perm := os.FileMode(0o644)
	if fi, err := os.Stat(path); err == nil {
		perm = fi.Mode().Perm()
	}
	tmp, err := os.CreateTemp(dir, ".agentic-*.tmp")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName)
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Chmod(tmpName, perm); err != nil {
		return err
	}
	return os.Rename(tmpName, path)
}
