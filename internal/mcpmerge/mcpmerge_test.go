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

func readSidecar(t *testing.T, path string) []string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var v struct {
		Servers []string `json:"servers"`
	}
	if err := json.Unmarshal(b, &v); err != nil {
		t.Fatalf("sidecar is not valid JSON: %v", err)
	}
	return v.Servers
}

// TestMergeCursorSidecarBootstraps: the first MergeCursor run against a target
// with no pre-existing sidecar must create one recording the managed set, and
// must not remove any pre-existing hand-added server (no retro-claiming).
func TestMergeCursorSidecarBootstraps(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "integrations", "gn", "mcp.stdio.json"),
		`{"mcpServers":{"gitnexus":{"command":"gn"}}}`)
	out := filepath.Join(root, "mcp.json")
	writeFile(t, out, `{"mcpServers":{"dora":{"command":"dora"}}}`)

	if _, err := os.Stat(sidecarPath(out)); !os.IsNotExist(err) {
		t.Fatal("sidecar unexpectedly pre-exists")
	}
	if err := MergeCursor(root, out); err != nil {
		t.Fatal(err)
	}

	servers := readSidecar(t, sidecarPath(out))
	if len(servers) != 1 || servers[0] != "gitnexus" {
		t.Errorf("sidecar not bootstrapped with the managed set, got %v", servers)
	}

	m := map[string]any{}
	b, _ := os.ReadFile(out)
	_ = json.Unmarshal(b, &m)
	mcp, _ := m["mcpServers"].(map[string]any)
	if _, ok := mcp["dora"]; !ok {
		t.Error("bootstrap run must not retro-claim/remove a pre-existing hand-added server")
	}
}

// TestMergeCursorSidecarRemovesStaleServer: once a sidecar exists, a server it
// recorded that is no longer produced by the fragments (its integration was
// deleted) must be removed from mcp.json on the next merge, while a genuinely
// hand-added server (never in the sidecar) survives.
func TestMergeCursorSidecarRemovesStaleServer(t *testing.T) {
	root := t.TempDir()
	fragPath := filepath.Join(root, "integrations", "gn", "mcp.stdio.json")
	writeFile(t, fragPath, `{"mcpServers":{"gitnexus":{"command":"gn"}}}`)
	out := filepath.Join(root, "mcp.json")

	// First run: bootstraps the sidecar with gitnexus managed.
	if err := MergeCursor(root, out); err != nil {
		t.Fatal(err)
	}
	// Simulate a user hand-adding their own server between runs.
	m := map[string]any{}
	b, _ := os.ReadFile(out)
	_ = json.Unmarshal(b, &m)
	mcp, _ := m["mcpServers"].(map[string]any)
	mcp["hand-added"] = map[string]any{"command": "custom"}
	nb, _ := json.Marshal(m)
	if err := os.WriteFile(out, nb, 0o644); err != nil {
		t.Fatal(err)
	}

	// Remove the integration fragment: gitnexus is no longer managed.
	if err := os.Remove(fragPath); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(filepath.Dir(fragPath)); err != nil {
		t.Fatal(err)
	}

	if err := MergeCursor(root, out); err != nil {
		t.Fatal(err)
	}

	b, _ = os.ReadFile(out)
	m = map[string]any{}
	_ = json.Unmarshal(b, &m)
	mcp, _ = m["mcpServers"].(map[string]any)
	if _, ok := mcp["gitnexus"]; ok {
		t.Error("stale managed server 'gitnexus' was not removed after its fragment was deleted")
	}
	if _, ok := mcp["hand-added"]; !ok {
		t.Error("hand-added server (never in the sidecar) must survive stale-server removal")
	}

	servers := readSidecar(t, sidecarPath(out))
	if len(servers) != 0 {
		t.Errorf("sidecar should now record no managed servers, got %v", servers)
	}
}
