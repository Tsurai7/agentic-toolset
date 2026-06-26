package hook

import (
	"bytes"
	"encoding/json"
	"testing"
)

// decide runs the hook over a Bash command and returns ("PASS"|"DENY"|"REWRITE",
// rewrittenCommand). External deps (lean-ctx, rtk) are stubbed by the caller.
func decide(command string) (decision, rewritten string) {
	raw, _ := json.Marshal(map[string]any{
		"tool_name":  "Bash",
		"tool_input": map[string]any{"command": command},
	})
	var out bytes.Buffer
	shellGuard(bytes.NewReader(raw), &out)
	if out.Len() == 0 {
		return "PASS", ""
	}
	var env decisionEnvelope
	if err := json.Unmarshal(out.Bytes(), &env); err != nil {
		return "BADJSON", out.String()
	}
	if env.HookSpecificOutput.PermissionDecision == "deny" {
		return "DENY", ""
	}
	cmd := ""
	if env.HookSpecificOutput.UpdatedInput != nil {
		cmd = env.HookSpecificOutput.UpdatedInput.Command
	}
	return "REWRITE", cmd
}

func TestShellGuard(t *testing.T) {
	// Isolate from the host: lean-ctx declines, rtk is present.
	leanCtxRewrite = func(raw []byte) ([]byte, bool) { return nil, false }
	hasRTK = func() bool { return true }

	cases := []struct {
		name     string
		cmd      string
		decision string
		rewrite  string // checked only when non-empty
	}{
		{"quoted-pattern grep not denied", `grep "foo.py" data.csv`, "REWRITE", `rtk grep "foo.py" data.csv`},
		{"real code-file grep denied", "grep pattern src/main.go", "DENY", ""},
		{"quoted pattern + code target denied", `grep "TODO" main.go`, "DENY", ""},
		{"non-code target not denied", "grep TODO notes.md", "REWRITE", "rtk grep TODO notes.md"},
		{"leading assignment passes through", "FOO=/tmp; echo $FOO", "PASS", ""},
		{"already-wrapped rtk", "rtk npm test", "PASS", ""},
		{"FOO=1 rtk is not double-wrapped", "FOO=1 rtk npm test", "PASS", ""},
		{"simple command wrapped", "python3 script.py", "REWRITE", "rtk python3 script.py"},
		{"variable use stays wrapped", `echo "$HOME"`, "REWRITE", `rtk echo "$HOME"`},
		{"heredoc fail-open", "cat <<EOF\nhi\nEOF", "PASS", ""},
		{"command-substitution fail-open", "echo $(date)", "PASS", ""},
		{"cd chain fail-open", "cd /tmp && ls", "PASS", ""},
	}
	for _, c := range cases {
		gotDec, gotCmd := decide(c.cmd)
		if gotDec != c.decision {
			t.Errorf("%s: command %q -> decision %q, want %q", c.name, c.cmd, gotDec, c.decision)
			continue
		}
		if c.rewrite != "" && gotCmd != c.rewrite {
			t.Errorf("%s: command %q -> rewrite %q, want %q", c.name, c.cmd, gotCmd, c.rewrite)
		}
	}
}

func TestNonBashToolPassesThrough(t *testing.T) {
	raw, _ := json.Marshal(map[string]any{
		"tool_name":  "Read",
		"tool_input": map[string]any{"command": "grep x main.go"},
	})
	var out bytes.Buffer
	shellGuard(bytes.NewReader(raw), &out)
	if out.Len() != 0 {
		t.Errorf("non-Bash tool should pass through with no output, got %q", out.String())
	}
}

func TestUnparseableInputFailsOpen(t *testing.T) {
	var out bytes.Buffer
	shellGuard(bytes.NewReader([]byte("not json")), &out)
	if out.Len() != 0 {
		t.Errorf("unparseable input should fail open, got %q", out.String())
	}
}

func TestLeanCtxRewriteHonored(t *testing.T) {
	leanCtxRewrite = func(raw []byte) ([]byte, bool) {
		return []byte(`{"hookSpecificOutput":{"updatedInput":{"command":"lean-ctx -c 'ls'"}}}`), true
	}
	hasRTK = func() bool { return true }
	defer func() { leanCtxRewrite = func(raw []byte) ([]byte, bool) { return nil, false } }()

	dec, cmd := decide("ls -la")
	if dec != "REWRITE" || cmd != "lean-ctx -c 'ls'" {
		t.Errorf("lean-ctx output should be honored verbatim, got (%s, %q)", dec, cmd)
	}
}
