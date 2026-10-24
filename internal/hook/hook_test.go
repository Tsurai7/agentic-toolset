package hook

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

// decide runs the hook over a Bash command and returns "PASS" or "DENY".
func decide(command string) string {
	raw, _ := json.Marshal(map[string]any{
		"tool_name":  "Bash",
		"tool_input": map[string]any{"command": command},
	})
	var out bytes.Buffer
	shellGuard(bytes.NewReader(raw), &out)
	if out.Len() == 0 {
		return "PASS"
	}
	var env decisionEnvelope
	if err := json.Unmarshal(out.Bytes(), &env); err != nil {
		return "BADJSON"
	}
	return strings.ToUpper(env.HookSpecificOutput.PermissionDecision)
}

func TestShellGuard(t *testing.T) {
	cases := []struct {
		name     string
		cmd      string
		decision string
	}{
		{"quoted-pattern grep not denied", `grep "foo.py" data.csv`, "PASS"},
		{"real code-file grep denied", "grep pattern src/main.go", "DENY"},
		{"quoted pattern + code target denied", `grep "TODO" main.go`, "DENY"},
		{"non-code target not denied", "grep TODO notes.md", "PASS"},
		// grep-in-argument-position: `grep` must be the command word (start of
		// string, or after a shell operator), not merely preceded by a space —
		// otherwise `git grep` is mistaken for a bare grep invocation.
		{"git grep in argument position not denied", "git grep TODO main.py", "PASS"},
		{"piped grep still denied", "cat main.go | grep TODO", "DENY"},
		{"leading assignment passes through", "FOO=/tmp; echo $FOO", "PASS"},
		{"already-wrapped rtk", "rtk npm test", "PASS"},
		{"FOO=1 rtk is not double-wrapped", "FOO=1 rtk npm test", "PASS"},
		{"simple command wrapped", "python3 script.py", "PASS"},
		{"variable use stays wrapped", `echo "$HOME"`, "PASS"},
		{"heredoc fail-open", "cat <<EOF\nhi\nEOF", "PASS"},
		{"command-substitution fail-open", "echo $(date)", "PASS"},
		{"cd chain fail-open", "cd /tmp && ls", "PASS"},
		// Order fix (issues/shell-guard-astgrep-order-bypass.md): the ast-grep
		// deny must fire even when the command is already rtk-wrapped
		// or carries a leading assignment.
		{"rtk-wrapped grep on code denied", "rtk grep -n foo internal/hook/hook.go", "DENY"},
		{"assignment + rtk-wrapped grep on code denied", "FOO=1 rtk grep TODO cmd/agentic/main.go", "DENY"},
		{"rtk-wrapped quoted-pattern grep not denied", `rtk grep "foo.py" data.csv`, "PASS"},
		{"rtk ls stays already-wrapped", "rtk ls -la", "PASS"},
		// Equals-token pass-through (issues/rtk-wrap-breaks-equals-words.md):
		// a bare `=`-leading token would trigger zsh equals-expansion inside
		// rtk's eval, so pass such commands through untouched.
		{"bare equals token passes through", "echo ===", "PASS"},
		{"equals token as separate arg passes through", "echo = separator", "PASS"},
		{"equals mid-word still wrapped", "echo a=b", "PASS"},
		{"baseline simple command still wrapped", "echo hi", "PASS"},
		{"leading assignment still passes through", "FOO=1 echo hi", "PASS"},
		// BUG-02: a bit-shift contains `<<` but must not be mangled — fail open
		// (run untouched) rather than the old glob's silent wrapping-skip.
		{"bit-shift fail-open (BUG-02)", "python3 -c 'print(1 << 3)'", "PASS"},
		// BUG-01: a real multiline command (decoded \n from the JSON) must fail
		// open, never get a literal-\n-mangled rewrite from string-munged JSON.
		{"plain multiline fail-open (BUG-01)", "echo a\necho b", "PASS"},
		// A1: complex-command fail-open must run before the ast-grep deny, so a
		// heredoc/multiline/cd-chain/$( )-containing grep-on-code command fails
		// open instead of being denied (issues/shell-guard-astgrep-order-bypass.md).
		{"multiline grep-on-code fails open (A1)", "grep TODO main.go\necho b", "PASS"},
		{"heredoc grep-on-code fails open (A1)", "grep TODO main.go <<EOF\nx\nEOF", "PASS"},
		{"cd-chain grep-on-code fails open (A1)", "cd src && grep TODO main.go", "PASS"},
		{"cmdsub grep-on-code fails open (A1)", "grep TODO main.go $(pwd)", "PASS"},
		{"heredoc-body false-positive fails open (A1)", "grep bug notes.txt <<EOF\nsee main.go\nEOF", "PASS"},
		// A3: a code extension mid-filename (backup/suffixed text file) must not
		// deny, but a code extension terminated by a pipe/semicolon still must.
		{"backup file .go.orig not denied (A3)", "grep foo main.go.orig", "PASS"},
		{"backup file .go.txt not denied (A3)", "grep TODO main.go.txt", "PASS"},
		{"backup file .py.bak not denied (A3)", "rg pat src/util.py.bak", "PASS"},
		{"unspaced pipe still denied (A3)", "grep foo main.go|head", "DENY"},
		{"semicolon still denied (A3)", "grep foo main.go;ls", "DENY"},
	}
	for _, c := range cases {
		if got := decide(c.cmd); got != c.decision {
			t.Errorf("%s: command %q -> decision %q, want %q", c.name, c.cmd, got, c.decision)
		}
	}
}

func TestClassify(t *testing.T) {
	cases := []struct {
		cmd  string
		want Decision
	}{
		{"", DecisionEmpty},
		{"grep TODO main.go", DecisionDenyGrepCode},
		{"rtk npm test", DecisionAlreadyWrapped},
		{"cat <<EOF\nhi\nEOF", DecisionFailOpenComplex},
		{"FOO=1 echo hi", DecisionFailOpenAssign},
		{"echo ===", DecisionFailOpenEquals},
		{"echo hi", DecisionWrap},
		// A1: complex-command fail-open must win over the ast-grep deny for
		// grep-on-code commands wrapped in a heredoc/multiline/cd-chain/$( ).
		{"grep TODO main.go\necho b", DecisionFailOpenComplex},
		{"grep TODO main.go <<EOF\nx\nEOF", DecisionFailOpenComplex},
		{"cd src && grep TODO main.go", DecisionFailOpenComplex},
		{"grep TODO main.go $(pwd)", DecisionFailOpenComplex},
		{"grep bug notes.txt <<EOF\nsee main.go\nEOF", DecisionFailOpenComplex},
		// A3: a code extension mid-filename must not deny; terminated by a pipe
		// still must.
		{"grep foo main.go.orig", DecisionWrap},
		{"grep foo main.go|head", DecisionDenyGrepCode},
	}
	for _, c := range cases {
		if got := Classify(c.cmd); got != c.want {
			t.Errorf("Classify(%q) = %q, want %q", c.cmd, got, c.want)
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
