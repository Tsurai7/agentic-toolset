package settings

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Merge then Unmerge must return the file to its user-only content: managed hooks
// and managed allow entries gone, user hook + env + deny + user allow intact.
func TestMergeThenUnmerge(t *testing.T) {
	dir := t.TempDir()
	frag := filepath.Join(dir, "frag.json")
	if err := os.WriteFile(frag, []byte(`{
      "hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "/x/providers/claude/hooks/shell-guard.sh"}]}
      ]},
      "permissions": {"allow": ["mcp__lean-ctx__ctx_read", "mcp__lean-ctx__ctx_search"]}
    }`), 0o644); err != nil {
		t.Fatal(err)
	}
	out := filepath.Join(dir, "settings.json")
	if err := os.WriteFile(out, []byte(`{
      "env": {"K": "v"},
      "hooks": {"PreToolUse": [
        {"matcher": "User", "hooks": [{"type": "command", "command": "/usr/bin/user.sh"}]}
      ]},
      "permissions": {"allow": ["Bash(x:*)"], "deny": ["Bash(rm:*)"]}
    }`), 0o644); err != nil {
		t.Fatal(err)
	}

	readBody := func() string {
		b, err := os.ReadFile(out)
		if err != nil {
			t.Fatal(err)
		}
		return string(b)
	}

	if err := Merge(frag, out); err != nil {
		t.Fatalf("Merge: %v", err)
	}
	if !strings.Contains(readBody(), "shell-guard.sh") {
		t.Fatal("merge did not add the managed hook")
	}

	if err := Unmerge(frag, out); err != nil {
		t.Fatalf("Unmerge: %v", err)
	}
	body := readBody()
	if strings.Contains(body, "shell-guard.sh") {
		t.Error("unmerge left the managed hook")
	}
	if strings.Contains(body, "ctx_read") {
		t.Error("unmerge left a managed allow entry")
	}
	if !strings.Contains(body, "user.sh") {
		t.Error("unmerge removed the user hook")
	}

	var m map[string]any
	if err := json.Unmarshal([]byte(body), &m); err != nil {
		t.Fatal(err)
	}
	if m["env"].(map[string]any)["K"] != "v" {
		t.Error("unmerge lost user env")
	}
	perms := m["permissions"].(map[string]any)
	allow := perms["allow"].([]any)
	if len(allow) != 1 || allow[0].(string) != "Bash(x:*)" {
		t.Errorf("unmerge allow = %v, want [Bash(x:*)]", allow)
	}
	deny := perms["deny"].([]any)
	if len(deny) != 1 || deny[0].(string) != "Bash(rm:*)" {
		t.Errorf("unmerge altered deny: %v", deny)
	}
}
