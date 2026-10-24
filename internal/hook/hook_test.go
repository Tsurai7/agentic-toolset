package hook

import (
	"bytes"
	"encoding/json"
	"os"
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
		// grep-in-argument-position: `grep` must be the command word (start of
		// string, or after a shell operator), not merely preceded by a space —
		// otherwise `git grep` is mistaken for a bare grep invocation.
		{"git grep in argument position not denied", "git grep TODO main.py", "REWRITE", "rtk git grep TODO main.py"},
		{"piped grep still denied", "cat main.go | grep TODO", "DENY", ""},
		{"leading assignment passes through", "FOO=/tmp; echo $FOO", "PASS", ""},
		{"already-wrapped rtk", "rtk npm test", "PASS", ""},
		{"FOO=1 rtk is not double-wrapped", "FOO=1 rtk npm test", "PASS", ""},
		{"simple command wrapped", "python3 script.py", "REWRITE", "rtk python3 script.py"},
		{"variable use stays wrapped", `echo "$HOME"`, "REWRITE", `rtk echo "$HOME"`},
		{"heredoc fail-open", "cat <<EOF\nhi\nEOF", "PASS", ""},
		{"command-substitution fail-open", "echo $(date)", "PASS", ""},
		{"cd chain fail-open", "cd /tmp && ls", "PASS", ""},
		// Order fix (issues/shell-guard-astgrep-order-bypass.md): the ast-grep
		// deny must fire even when the command is already rtk/lean-ctx-wrapped
		// or carries a leading assignment.
		{"rtk-wrapped grep on code denied", "rtk grep -n foo internal/hook/hook.go", "DENY", ""},
		{"lean-ctx-wrapped grep on code denied", "lean-ctx grep -rn foo src/main.go", "DENY", ""},
		{"assignment + rtk-wrapped grep on code denied", "FOO=1 rtk grep TODO cmd/agentic/main.go", "DENY", ""},
		{"rtk-wrapped quoted-pattern grep not denied", `rtk grep "foo.py" data.csv`, "PASS", ""},
		{"rtk ls stays already-wrapped", "rtk ls -la", "PASS", ""},
		// Equals-token pass-through (issues/rtk-wrap-breaks-equals-words.md):
		// a bare `=`-leading token would trigger zsh equals-expansion inside
		// rtk's eval, so pass such commands through untouched.
		{"bare equals token passes through", "echo ===", "PASS", ""},
		{"equals token as separate arg passes through", "echo = separator", "PASS", ""},
		{"equals mid-word still wrapped", "echo a=b", "REWRITE", "rtk echo a=b"},
		{"baseline simple command still wrapped", "echo hi", "REWRITE", "rtk echo hi"},
		{"leading assignment still passes through", "FOO=1 echo hi", "PASS", ""},
		// BUG-02: a bit-shift contains `<<` but must not be mangled — fail open
		// (run untouched) rather than the old glob's silent wrapping-skip.
		{"bit-shift fail-open (BUG-02)", "python3 -c 'print(1 << 3)'", "PASS", ""},
		// BUG-01: a real multiline command (decoded \n from the JSON) must fail
		// open, never get a literal-\n-mangled rewrite from string-munged JSON.
		{"plain multiline fail-open (BUG-01)", "echo a\necho b", "PASS", ""},
		// A1: complex-command fail-open must run before the ast-grep deny, so a
		// heredoc/multiline/cd-chain/$( )-containing grep-on-code command fails
		// open instead of being denied (issues/shell-guard-astgrep-order-bypass.md).
		{"multiline grep-on-code fails open (A1)", "grep TODO main.go\necho b", "PASS", ""},
		{"heredoc grep-on-code fails open (A1)", "grep TODO main.go <<EOF\nx\nEOF", "PASS", ""},
		{"cd-chain grep-on-code fails open (A1)", "cd src && grep TODO main.go", "PASS", ""},
		{"cmdsub grep-on-code fails open (A1)", "grep TODO main.go $(pwd)", "PASS", ""},
		{"heredoc-body false-positive fails open (A1)", "grep bug notes.txt <<EOF\nsee main.go\nEOF", "PASS", ""},
		// A3: a code extension mid-filename (backup/suffixed text file) must not
		// deny, but a code extension terminated by a pipe/semicolon still must.
		{"backup file .go.orig not denied (A3)", "grep foo main.go.orig", "REWRITE", "rtk grep foo main.go.orig"},
		{"backup file .go.txt not denied (A3)", "grep TODO main.go.txt", "REWRITE", "rtk grep TODO main.go.txt"},
		{"backup file .py.bak not denied (A3)", "rg pat src/util.py.bak", "REWRITE", "rtk rg pat src/util.py.bak"},
		{"unspaced pipe still denied (A3)", "grep foo main.go|head", "DENY", ""},
		{"semicolon still denied (A3)", "grep foo main.go;ls", "DENY", ""},
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

// A7: a panic anywhere in the hook path must fail open (return 0), not
// propagate — an unrecovered panic would otherwise exit the process non-zero,
// which Claude Code treats as a blocking hook error.
func TestPanicFailsOpen(t *testing.T) {
	leanCtxRewrite = func(raw []byte) ([]byte, bool) { panic("boom") }
	hasRTK = func() bool { return true }
	defer func() { leanCtxRewrite = func(raw []byte) ([]byte, bool) { return nil, false } }()

	raw, _ := json.Marshal(map[string]any{
		"tool_name":  "Bash",
		"tool_input": map[string]any{"command": "ls -la"},
	})

	r, w, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.Write(raw); err != nil {
		t.Fatal(err)
	}
	w.Close()
	origStdin := os.Stdin
	os.Stdin = r
	defer func() { os.Stdin = origStdin }()

	code := Main([]string{"shell-guard"})
	if code != 0 {
		t.Errorf("Main should fail open (return 0) on panic, got %d", code)
	}
}
