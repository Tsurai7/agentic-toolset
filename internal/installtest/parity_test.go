package installtest

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"regexp"
	"testing"

	"github.com/Tsurai7/agentic-cfg/internal/claudemd"
	"github.com/Tsurai7/agentic-cfg/internal/mcpmerge"
	"github.com/Tsurai7/agentic-cfg/internal/settings"
)

// These tests pin the Go ports to the Python reference scripts during the
// transition: if a port drifts, the parity test fails. They need python3 (present
// on CI runners) and skip otherwise.

func needPython(t *testing.T) {
	t.Helper()
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not available")
	}
}

func runPy(t *testing.T, root, script string, args ...string) {
	t.Helper()
	all := append([]string{filepath.Join(root, "providers", "shared", script)}, args...)
	if out, err := exec.Command("python3", all...).CombinedOutput(); err != nil {
		t.Fatalf("%s failed: %v\n%s", script, err, out)
	}
}

func parsed(t *testing.T, path string) any {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var v any
	if err := json.Unmarshal(b, &v); err != nil {
		t.Fatalf("invalid JSON in %s: %v", path, err)
	}
	return v
}

func readStr(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func mustWrite(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

var atLineRe = regexp.MustCompile(`(?m)^@.*$`)

func TestSettingsParityWithPython(t *testing.T) {
	needPython(t)
	root := repoRoot(t)
	frag := filepath.Join(root, "providers", "claude", "settings.hooks.json")
	existing := `{"env":{"X":"1"},"hooks":{"PreToolUse":[` +
		`{"matcher":"Bash","hooks":[{"type":"command","command":"/old/providers/claude/hooks/shell-guard.sh"}]},` +
		`{"matcher":"Write","hooks":[{"type":"command","command":"/u/audit.sh"}]}],` +
		`"Notification":[{"matcher":".*","hooks":[{"type":"command","command":"/u/notify.sh"}]}]},` +
		`"permissions":{"allow":["mcp__c__x"],"deny":["Bash(rm -rf /)"]}}`
	d := t.TempDir()
	goF, pyF := filepath.Join(d, "go.json"), filepath.Join(d, "py.json")
	mustWrite(t, goF, existing)
	mustWrite(t, pyF, existing)

	if err := settings.Merge(frag, goF); err != nil {
		t.Fatal(err)
	}
	runPy(t, root, "merge-settings.py", frag, pyF)

	if !reflect.DeepEqual(parsed(t, goF), parsed(t, pyF)) {
		t.Errorf("merge-settings parity mismatch\nGO: %s\nPY: %s", readStr(t, goF), readStr(t, pyF))
	}
}

func TestMcpParityWithPython(t *testing.T) {
	needPython(t)
	root := repoRoot(t)
	seed := `{"mcpServers":{"dora":{"command":"dora"}},"other":1}`
	d := t.TempDir()
	goF, pyF := filepath.Join(d, "go.json"), filepath.Join(d, "py.json")
	mustWrite(t, goF, seed)
	mustWrite(t, pyF, seed)

	if err := mcpmerge.MergeCursor(root, goF); err != nil {
		t.Fatal(err)
	}
	runPy(t, root, "merge-mcp.py", root, pyF)

	if !reflect.DeepEqual(parsed(t, goF), parsed(t, pyF)) {
		t.Errorf("merge-mcp parity mismatch\nGO: %s\nPY: %s", readStr(t, goF), readStr(t, pyF))
	}
}

// writeFragment writes a single-server integration fragment under
// <agenticRoot>/integrations/<dir>/mcp.stdio.json.
func writeFragment(t *testing.T, agenticRoot, dir, server, config string) {
	t.Helper()
	p := filepath.Join(agenticRoot, "integrations", dir, "mcp.stdio.json")
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	mustWrite(t, p, `{"mcpServers":{"`+server+`":`+config+`}}`)
}

func sidecarServers(t *testing.T, mcpJSONPath string) []string {
	t.Helper()
	sidecar := filepath.Join(filepath.Dir(mcpJSONPath), ".agentic-managed.json")
	b, err := os.ReadFile(sidecar)
	if err != nil {
		t.Fatalf("read sidecar %s: %v", sidecar, err)
	}
	var v struct {
		Servers []string `json:"servers"`
	}
	if err := json.Unmarshal(b, &v); err != nil {
		t.Fatalf("sidecar not valid JSON: %v", err)
	}
	return v.Servers
}

// TestMcpSidecarParityWithPython extends the Go<->Python parity coverage to
// plan 06 change 9's ported cursor sidecar behavior (originally Python-only
// per plan 08): bootstrap (first run, no retro-claim), stale-managed-server
// removal once a fragment is deleted, and a hand-added server surviving both.
// Each independently-driven agentic-root fixture (own integrations/ dir) is
// merged through both the Go and Python paths and the resulting mcp.json +
// sidecar are compared byte-for-byte.
func TestMcpSidecarParityWithPython(t *testing.T) {
	needPython(t)
	scriptRoot := repoRoot(t) // where providers/shared/merge-mcp.py itself lives

	newFixtureRoot := func(t *testing.T) string {
		t.Helper()
		r := t.TempDir()
		writeFragment(t, r, "gn", "gitnexus", `{"command":"gn"}`)
		return r
	}

	t.Run("bootstrap_no_retro_claim", func(t *testing.T) {
		goRoot, pyRoot := newFixtureRoot(t), newFixtureRoot(t)
		goDir, pyDir := t.TempDir(), t.TempDir() // separate dirs: each gets its own sidecar
		goF, pyF := filepath.Join(goDir, "mcp.json"), filepath.Join(pyDir, "mcp.json")
		seed := `{"mcpServers":{"hand-added":{"command":"custom"}}}`
		mustWrite(t, goF, seed)
		mustWrite(t, pyF, seed)

		if err := mcpmerge.MergeCursor(goRoot, goF); err != nil {
			t.Fatal(err)
		}
		runPy(t, scriptRoot, "merge-mcp.py", pyRoot, pyF)

		if !reflect.DeepEqual(parsed(t, goF), parsed(t, pyF)) {
			t.Errorf("mcp.json parity mismatch (bootstrap)\nGO: %s\nPY: %s", readStr(t, goF), readStr(t, pyF))
		}
		goSidecar, pySidecar := sidecarServers(t, goF), sidecarServers(t, pyF)
		if !reflect.DeepEqual(goSidecar, pySidecar) {
			t.Errorf("sidecar parity mismatch (bootstrap): GO=%v PY=%v", goSidecar, pySidecar)
		}
		if len(goSidecar) != 1 || goSidecar[0] != "gitnexus" {
			t.Errorf("bootstrap sidecar should record the managed set, got %v", goSidecar)
		}
	})

	t.Run("stale_removal_and_hand_added_survival", func(t *testing.T) {
		goRoot, pyRoot := newFixtureRoot(t), newFixtureRoot(t)
		goDir, pyDir := t.TempDir(), t.TempDir() // separate dirs: each gets its own sidecar
		goF, pyF := filepath.Join(goDir, "mcp.json"), filepath.Join(pyDir, "mcp.json")
		mustWrite(t, goF, `{"mcpServers":{}}`)
		mustWrite(t, pyF, `{"mcpServers":{}}`)

		// First pass: bootstraps both sidecars with gitnexus managed.
		if err := mcpmerge.MergeCursor(goRoot, goF); err != nil {
			t.Fatal(err)
		}
		runPy(t, scriptRoot, "merge-mcp.py", pyRoot, pyF)

		// Hand-add a server directly to each output between runs.
		for _, f := range []string{goF, pyF} {
			m := parsed(t, f).(map[string]any)
			servers, _ := m["mcpServers"].(map[string]any)
			servers["hand-added"] = map[string]any{"command": "custom"}
			b, err := json.Marshal(m)
			if err != nil {
				t.Fatal(err)
			}
			mustWrite(t, f, string(b))
		}

		// Delete the gitnexus fragment from each fixture root: no longer managed.
		if err := os.RemoveAll(filepath.Join(goRoot, "integrations", "gn")); err != nil {
			t.Fatal(err)
		}
		if err := os.RemoveAll(filepath.Join(pyRoot, "integrations", "gn")); err != nil {
			t.Fatal(err)
		}

		// Second pass: gitnexus (stale, sidecar-tracked) must be removed;
		// hand-added (never tracked) must survive.
		if err := mcpmerge.MergeCursor(goRoot, goF); err != nil {
			t.Fatal(err)
		}
		runPy(t, scriptRoot, "merge-mcp.py", pyRoot, pyF)

		if !reflect.DeepEqual(parsed(t, goF), parsed(t, pyF)) {
			t.Errorf("mcp.json parity mismatch (stale removal)\nGO: %s\nPY: %s", readStr(t, goF), readStr(t, pyF))
		}
		goSidecar, pySidecar := sidecarServers(t, goF), sidecarServers(t, pyF)
		if !reflect.DeepEqual(goSidecar, pySidecar) {
			t.Errorf("sidecar parity mismatch (stale removal): GO=%v PY=%v", goSidecar, pySidecar)
		}

		goServers, _ := parsed(t, goF).(map[string]any)["mcpServers"].(map[string]any)
		if _, ok := goServers["gitnexus"]; ok {
			t.Error("Go path did not remove the stale managed server")
		}
		if _, ok := goServers["hand-added"]; !ok {
			t.Error("Go path removed the hand-added server (should survive)")
		}
	})
}

func TestClaudeMdParityWithPython(t *testing.T) {
	needPython(t)
	root := repoRoot(t)
	d := t.TempDir()
	gen := filepath.Join(d, "agentic-cfg.generated.md")
	mustWrite(t, gen, "GENERATED\n")

	cases := map[string]string{
		"fresh":  "",
		"user":   "# notes\nkeep me\n",
		"legacy": "<!-- Generated by agentic bin/install.sh -->\n\ninline\n## Principles (always-on)\nLEGACY\n",
	}
	for name, existing := range cases {
		goF, pyF := filepath.Join(d, name+"_go.md"), filepath.Join(d, name+"_py.md")
		for _, f := range []string{goF, pyF} {
			if existing == "" {
				os.Remove(f)
			} else {
				mustWrite(t, f, existing)
			}
		}
		if err := claudemd.Ensure(gen, goF); err != nil {
			t.Fatal(err)
		}
		runPy(t, root, "merge-claude-md.py", gen, pyF)
		// Normalize the @import path (Go uses abs, Python resolves symlinks).
		g := atLineRe.ReplaceAllString(readStr(t, goF), "@GEN")
		p := atLineRe.ReplaceAllString(readStr(t, pyF), "@GEN")
		if g != p {
			t.Errorf("merge-claude-md parity mismatch (%s)\nGO:\n%s\nPY:\n%s", name, g, p)
		}
	}
}
