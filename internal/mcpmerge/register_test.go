package mcpmerge

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// fakeClaudeScript is a minimal stand-in for the `claude` CLI's `mcp remove` /
// `mcp add-json --scope user` subcommands, backed by a real
// $CLAUDE_CONFIG_DIR/.claude.json so registeredServerJSON can read it exactly
// like it would the real CLI's file. It fails the FIRST `add-json` call for the
// server named by $FAIL_SERVER_ONCE (tracked via a marker file so a restore
// retry succeeds), to drive the registration-failure-and-restore drill.
const fakeClaudeScript = `#!/usr/bin/env bash
set -euo pipefail
cfg="${CLAUDE_CONFIG_DIR:?}/.claude.json"
state="${CLAUDE_CONFIG_DIR}/.fake-claude-state"
mkdir -p "$state"
[[ -f "$cfg" ]] || echo '{"mcpServers":{}}' > "$cfg"

if [[ "$1" == "mcp" && "$2" == "remove" ]]; then
  name="$3"
  python3 -c "
import json
p = '$cfg'
d = json.load(open(p))
d.setdefault('mcpServers', {}).pop('$name', None)
json.dump(d, open(p, 'w'))
"
  exit 0
elif [[ "$1" == "mcp" && "$2" == "add-json" ]]; then
  name="$3"
  payload="$4"
  marker="${state}/failed-once-${name}"
  if [[ "${FAIL_SERVER_ONCE:-}" == "$name" && ! -f "$marker" ]]; then
    touch "$marker"
    echo "simulated add-json failure for $name" >&2
    exit 1
  fi
  python3 -c "
import json
p = '$cfg'
d = json.load(open(p))
d.setdefault('mcpServers', {})['$name'] = json.loads('''$payload''')
json.dump(d, open(p, 'w'))
"
  exit 0
fi
echo "fake claude: unhandled args: $*" >&2
exit 1
`

// installFakeClaude writes the fake claude script into a temp bin dir, prepends
// it to PATH, and points CLAUDE_CONFIG_DIR at a fresh temp home. Returns the
// path to the fake .claude.json.
func installFakeClaude(t *testing.T) (configDir, claudeJSON string) {
	t.Helper()
	if _, err := os.Stat("/usr/bin/env"); err != nil {
		t.Skip("no /usr/bin/env (needs a POSIX shell environment)")
	}
	if runtime.GOOS == "windows" {
		t.Skip("fake claude script needs bash")
	}
	bin := t.TempDir()
	script := filepath.Join(bin, "claude")
	if err := os.WriteFile(script, []byte(fakeClaudeScript), 0o755); err != nil {
		t.Fatal(err)
	}
	configDir = t.TempDir()
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("CLAUDE_CONFIG_DIR", configDir)
	return configDir, filepath.Join(configDir, ".claude.json")
}

// TestRegisterClaudeUserRestoresOnFailureAndContinues drives the plan 06 change 2
// drill: server-a's add-json fails once. Its PRIOR registration must be
// restored (not left unregistered), server-b (ordered after it) must still be
// processed, and the function must return a non-nil error naming server-a.
func TestRegisterClaudeUserRestoresOnFailureAndContinues(t *testing.T) {
	_, claudeJSON := installFakeClaude(t)
	t.Setenv("FAIL_SERVER_ONCE", "server-a")

	// Pre-seed a prior registration for server-a with a distinguishable payload.
	if err := os.WriteFile(claudeJSON,
		[]byte(`{"mcpServers":{"server-a":{"command":"/old/path/a","args":["--old"]}}}`), 0o644); err != nil {
		t.Fatal(err)
	}

	root := t.TempDir()
	writeFile(t, filepath.Join(root, "integrations", "a", "mcp.stdio.json"),
		`{"mcpServers":{"server-a":{"command":"/new/path/a","args":["--new"]}}}`)
	writeFile(t, filepath.Join(root, "integrations", "b", "mcp.stdio.json"),
		`{"mcpServers":{"server-b":{"command":"/path/b"}}}`)

	err := RegisterClaudeUser(root)
	if err == nil {
		t.Fatal("expected a non-nil error naming the failed server")
	}
	if !strings.Contains(err.Error(), "server-a") {
		t.Errorf("error does not name the failed server: %v", err)
	}

	b, readErr := os.ReadFile(claudeJSON)
	if readErr != nil {
		t.Fatal(readErr)
	}
	var final map[string]any
	if unmarshalErr := json.Unmarshal(b, &final); unmarshalErr != nil {
		t.Fatalf("final config is not valid JSON: %v", unmarshalErr)
	}
	servers, _ := final["mcpServers"].(map[string]any)

	a, ok := servers["server-a"].(map[string]any)
	if !ok {
		t.Fatal("server-a is unregistered after the failed add — restore did not happen")
	}
	if a["command"] != "/old/path/a" {
		t.Errorf("server-a was not restored to its prior registration, got %v", a)
	}

	b2, ok := servers["server-b"].(map[string]any)
	if !ok {
		t.Fatal("server-b was not registered — a failure on server-a must not abort the rest of the loop")
	}
	if b2["command"] != "/path/b" {
		t.Errorf("server-b registered with unexpected config: %v", b2)
	}
}

// TestRegisterClaudeUserSucceedsCleanly is the control case: no injected
// failure, both servers register, function returns nil.
func TestRegisterClaudeUserSucceedsCleanly(t *testing.T) {
	_, claudeJSON := installFakeClaude(t)

	root := t.TempDir()
	writeFile(t, filepath.Join(root, "integrations", "a", "mcp.stdio.json"),
		`{"mcpServers":{"server-a":{"command":"/path/a"}}}`)

	if err := RegisterClaudeUser(root); err != nil {
		t.Fatalf("RegisterClaudeUser: %v", err)
	}

	b, err := os.ReadFile(claudeJSON)
	if err != nil {
		t.Fatal(err)
	}
	var final map[string]any
	if err := json.Unmarshal(b, &final); err != nil {
		t.Fatalf("final config is not valid JSON: %v", err)
	}
	servers, _ := final["mcpServers"].(map[string]any)
	if _, ok := servers["server-a"]; !ok {
		t.Error("server-a not registered")
	}
}
