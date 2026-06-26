package mcpmerge

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/Tsurai7/agentic-cfg/internal/jsonorder"
)

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestSubstitute(t *testing.T) {
	env := map[string]string{"NPX": "/usr/bin/npx", "X": "y"}
	in := map[string]any{"command": "__NPX__", "args": []any{"-y", "__X__pkg"}}
	out := substitute(in, env).(map[string]any)
	if out["command"] != "/usr/bin/npx" {
		t.Errorf("string leaf not substituted: %v", out["command"])
	}
	if out["args"].([]any)[1] != "ypkg" {
		t.Errorf("array leaf not substituted: %v", out["args"])
	}
}

func TestFilterClaudeConfigStripsAutoApprove(t *testing.T) {
	raw := json.RawMessage(`{"command":"x","args":["a"],"env":{"K":"v"},"autoApprove":["t1"]}`)
	b, err := filterClaudeConfig(raw)
	if err != nil {
		t.Fatal(err)
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatalf("filtered payload is not valid JSON: %v", err)
	}
	if _, ok := m["autoApprove"]; ok {
		t.Error("autoApprove not stripped")
	}
	if m["command"] != "x" {
		t.Error("command field dropped")
	}
}

func TestCollectFragmentsOrder(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "a", "mcp.stdio.json"), `{"mcpServers":{"alpha":{"command":"a"}}}`)
	writeFile(t, filepath.Join(root, "b", "mcp.stdio.json"), `{"mcpServers":{"beta":{"command":"b"}}}`)
	m, err := collectFragments(root)
	if err != nil {
		t.Fatal(err)
	}
	if k := m.Keys(); len(k) != 2 || k[0] != "alpha" || k[1] != "beta" {
		t.Errorf("unexpected servers/order: %v", k)
	}
}

func TestCollectFragmentsExclude(t *testing.T) {
	t.Setenv("AGENTIC_MCP_EXCLUDE", "lean-ctx")
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "leanctx", "mcp.stdio.json"), `{"mcpServers":{"lean-ctx":{"command":"lc"}}}`)
	writeFile(t, filepath.Join(root, "gn", "mcp.stdio.json"), `{"mcpServers":{"gitnexus":{"command":"gn"}}}`)
	m, err := collectFragments(root)
	if err != nil {
		t.Fatal(err)
	}
	if k := m.Keys(); len(k) != 1 || k[0] != "gitnexus" {
		t.Errorf("expected only gitnexus after excluding lean-ctx, got: %v", k)
	}
}

func TestMergeCursorPreservesHandAdded(t *testing.T) {
	t.Setenv("NPX", "/test/npx")
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "integrations", "gitnexus", "mcp.stdio.json"),
		`{"mcpServers":{"gitnexus":{"command":"__NPX__","args":["-y","gitnexus"]}}}`)
	writeFile(t, filepath.Join(root, "providers", "cursor", "mcp.overlay.json"), `{"mcpServers":{}}`)
	out := filepath.Join(root, "mcp.json")
	writeFile(t, out, `{"mcpServers":{"dora":{"command":"dora"}}}`)

	if err := MergeCursor(root, out); err != nil {
		t.Fatal(err)
	}

	b, _ := os.ReadFile(out)
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatalf("output not valid JSON: %v", err)
	}
	servers, _ := m["mcpServers"].(map[string]any)
	if _, ok := servers["dora"]; !ok {
		t.Error("hand-added server 'dora' not preserved")
	}
	gn, ok := servers["gitnexus"].(map[string]any)
	if !ok {
		t.Fatal("managed server 'gitnexus' missing")
	}
	if gn["command"] != "/test/npx" {
		t.Errorf("placeholder not substituted: %v", gn["command"])
	}

	// order: existing 'dora' before appended managed 'gitnexus'
	top := jsonorder.New()
	_ = json.Unmarshal(b, top)
	sraw, _ := top.GetRaw("mcpServers")
	sm := jsonorder.New()
	_ = json.Unmarshal(sraw, sm)
	if k := sm.Keys(); len(k) != 2 || k[0] != "dora" || k[1] != "gitnexus" {
		t.Errorf("server order not preserved: %v", k)
	}
}

func TestMergeCursorIdempotent(t *testing.T) {
	t.Setenv("NPX", "/test/npx")
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "integrations", "gn", "mcp.stdio.json"),
		`{"mcpServers":{"gitnexus":{"command":"__NPX__"}}}`)
	writeFile(t, filepath.Join(root, "providers", "cursor", "mcp.overlay.json"), `{"mcpServers":{}}`)
	out := filepath.Join(root, "mcp.json")

	if err := MergeCursor(root, out); err != nil {
		t.Fatal(err)
	}
	first, _ := os.ReadFile(out)
	if err := MergeCursor(root, out); err != nil {
		t.Fatal(err)
	}
	second, _ := os.ReadFile(out)
	if !bytes.Equal(first, second) {
		t.Errorf("not idempotent:\nfirst:\n%s\nsecond:\n%s", first, second)
	}
}
