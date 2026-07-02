// Package hook implements the PreToolUse Bash hook — the Go port of
// providers/claude/hooks/shell-guard.sh.
//
// It reads the hook JSON from stdin with a real JSON parser (eliminating the
// grep/sed fragility of the shell version) and writes the hook decision envelope
// to stdout. Behavior mirrors the fixed shell hook: an ast-grep deny for
// code-targeted greps, a lean-ctx delegate, then an rtk fallback — with fail-open
// on complex commands and a leading-assignment guard so a naive wrapper never
// mangles a command.
package hook

import (
	"bytes"
	"io"
	"os"
	"os/exec"
	"regexp"
	"strings"

	"github.com/bytedance/sonic"
)

// Main dispatches `agentic hook <name>`.
func Main(args []string) int {
	name := ""
	if len(args) > 0 {
		name = args[0]
	}
	switch name {
	case "shell-guard":
		return shellGuard(os.Stdin, os.Stdout)
	default:
		return 0 // unknown hook name: no-op (fail open)
	}
}

type hookInput struct {
	ToolName  string `json:"tool_name"`
	ToolInput struct {
		Command string `json:"command"`
	} `json:"tool_input"`
}

var (
	codeExtRe       = regexp.MustCompile(`\.(go|cs|py|js|jsx|ts|tsx|java|kt|rb|rs|c|h|cc|cpp|hpp|php|swift|scala|sql|vue)(\b|['"]|$)`)
	leadingAssignRe = regexp.MustCompile(`^\s*[A-Za-z_][A-Za-z0-9_]*=`)
	assignTokenRe   = regexp.MustCompile(`^\s*[A-Za-z_][A-Za-z0-9_]*=\S*\s+`)
	quotedRe        = regexp.MustCompile(`'[^']*'|"[^"]*"`)
	equalsTokenRe   = regexp.MustCompile(`(^|\s)=`)
)

// GrepTokenRe matches a bare grep/egrep/fgrep/rg invocation as the command word
// (start of string or after a shell operator) — exported so internal/gain can
// tally grep/rg adoption without duplicating the pattern.
var GrepTokenRe = regexp.MustCompile("(^|[|;`]|&&|\\|\\||\\$\\()\\s*(grep|egrep|fgrep|rg)(\\s|$)")

var grepTokenRe = GrepTokenRe

// leanCtxRewrite delegates the raw hook input to `lean-ctx hook rewrite`,
// honoring its output only when it actually rewrote the command. Overridable in
// tests.
var leanCtxRewrite = func(raw []byte) ([]byte, bool) {
	if _, err := exec.LookPath("lean-ctx"); err != nil {
		return nil, false
	}
	cmd := exec.Command("lean-ctx", "hook", "rewrite")
	cmd.Stdin = bytes.NewReader(raw)
	out, err := cmd.Output()
	if err != nil {
		return nil, false
	}
	if bytes.Contains(out, []byte("updatedInput")) || bytes.Contains(out, []byte("updated_input")) {
		return out, true
	}
	return nil, false
}

// hasRTK reports whether rtk is on PATH. Overridable in tests.
var hasRTK = func() bool {
	_, err := exec.LookPath("rtk")
	return err == nil
}

// Decision classifies what the shell-guard would do with a Bash command.
type Decision string

const (
	DecisionEmpty           Decision = "empty"
	DecisionDenyGrepCode    Decision = "deny-grep-on-code"
	DecisionAlreadyWrapped  Decision = "already-wrapped"
	DecisionFailOpenComplex Decision = "failopen-complex" // heredoc/multiline/$( )/backtick/cd
	DecisionFailOpenAssign  Decision = "failopen-assign"  // leading VAR= (rtk fallback guard)
	DecisionFailOpenEquals  Decision = "failopen-equals"  // bare =-leading token (plan 02)
	DecisionWrap            Decision = "wrap"             // would be wrapped (lean-ctx or rtk)
)

// Classify returns the decision for a command, matching shellGuard's order
// exactly (deny -> already-wrapped -> fail-open-complex -> fail-open-assign ->
// fail-open-equals -> wrap). It does no I/O, so it cannot distinguish a
// lean-ctx wrap from an rtk wrap — both collapse to DecisionWrap.
func Classify(cmd string) Decision {
	if strings.TrimSpace(cmd) == "" {
		return DecisionEmpty
	}

	// 1. ast-grep guard: deny only when grep/rg targets a code FILE. Evaluated
	// against a normalized command (leading VAR= assignments and rtk/lean-ctx
	// wrapper prefixes stripped) so an already-wrapped `rtk grep … foo.go` cannot
	// bypass the deny by skipping straight to the already-wrapped exit below. A
	// code extension inside a quoted search pattern is ignored.
	normalized := stripWrappers(cmd)
	if grepTokenRe.MatchString(normalized) && codeExtRe.MatchString(quotedRe.ReplaceAllString(normalized, "")) {
		return DecisionDenyGrepCode
	}

	// Already wrapped (after stripping any leading VAR= assignments) -> never
	// double-wrap. Runs after the deny above so a pre-wrapped grep-on-code
	// command cannot skip the guard.
	if w := stripLeadingAssignments(cmd); strings.HasPrefix(w, "rtk ") || strings.HasPrefix(w, "lean-ctx ") {
		return DecisionAlreadyWrapped
	}

	// 2. lean-ctx delegate / rtk fallback candidates below this point. Complex
	// commands a wrapper would mangle -> fail open (run untouched).
	if strings.Contains(cmd, "<<") || strings.Contains(cmd, "\n") ||
		strings.Contains(cmd, "$(") || strings.Contains(cmd, "`") ||
		strings.HasPrefix(cmd, "cd ") || strings.Contains(cmd, "&& cd ") || strings.Contains(cmd, "; cd ") {
		return DecisionFailOpenComplex
	}

	// A leading assignment would be lost by a naive prefix, so pass it through
	// untouched instead.
	if leadingAssignRe.MatchString(cmd) {
		return DecisionFailOpenAssign
	}
	// A bare `=`-leading token triggers zsh equals-expansion inside rtk's eval
	// (issues/rtk-wrap-breaks-equals-words.md); pass such a command through
	// untouched rather than mangle it. `=` inside quotes is an acceptable
	// false-positive here — correctness beats compression.
	if equalsTokenRe.MatchString(cmd) {
		return DecisionFailOpenEquals
	}
	return DecisionWrap
}

func shellGuard(stdin io.Reader, stdout io.Writer) int {
	raw, err := io.ReadAll(stdin)
	if err != nil {
		return 0
	}
	var in hookInput
	if err := sonic.Unmarshal(raw, &in); err != nil {
		return 0 // unparseable input: fail open
	}
	switch in.ToolName {
	case "Bash", "bash", "PowerShell", "powershell":
	default:
		return 0
	}
	cmd := in.ToolInput.Command

	switch Classify(cmd) {
	case DecisionEmpty, DecisionAlreadyWrapped, DecisionFailOpenComplex, DecisionFailOpenAssign, DecisionFailOpenEquals:
		return 0
	case DecisionDenyGrepCode:
		writeDeny(stdout)
		return 0
	}

	// DecisionWrap: try lean-ctx first (it safely wraps a whole command), then
	// fall back to rtk.
	if out, ok := leanCtxRewrite(raw); ok {
		_, _ = stdout.Write(out)
		return 0
	}
	if !hasRTK() {
		return 0
	}
	writeRewrite(stdout, "rtk "+cmd)
	return 0
}

func stripLeadingAssignments(s string) string {
	for {
		m := assignTokenRe.FindString(s)
		if m == "" {
			return strings.TrimLeft(s, " \t")
		}
		s = s[len(m):]
	}
}

// stripWrappers strips leading VAR= assignments and rtk/lean-ctx wrapper
// prefixes repeatedly until fixpoint, so e.g. `FOO=1 rtk grep …` normalizes to
// `grep …` for guards that must see through an already-wrapped command.
func stripWrappers(s string) string {
	for {
		next := stripLeadingAssignments(s)
		switch {
		case strings.HasPrefix(next, "rtk "):
			next = next[len("rtk "):]
		case strings.HasPrefix(next, "lean-ctx "):
			next = next[len("lean-ctx "):]
		}
		if next == s {
			return next
		}
		s = next
	}
}

const astGrepReason = "Use ast-grep for structural code search: sg -p '<pattern>' -l <lang>. Plain grep is only for non-code text/logs (see the ast-grep + tool-precedence rules)."

type decisionEnvelope struct {
	HookSpecificOutput struct {
		HookEventName            string        `json:"hookEventName"`
		PermissionDecision       string        `json:"permissionDecision"`
		PermissionDecisionReason string        `json:"permissionDecisionReason,omitempty"`
		UpdatedInput             *updatedInput `json:"updatedInput,omitempty"`
	} `json:"hookSpecificOutput"`
}

type updatedInput struct {
	Command string `json:"command"`
}

func writeDeny(w io.Writer) {
	var e decisionEnvelope
	e.HookSpecificOutput.HookEventName = "PreToolUse"
	e.HookSpecificOutput.PermissionDecision = "deny"
	e.HookSpecificOutput.PermissionDecisionReason = astGrepReason
	b, _ := sonic.Marshal(e)
	_, _ = w.Write(b)
}

func writeRewrite(w io.Writer, command string) {
	var e decisionEnvelope
	e.HookSpecificOutput.HookEventName = "PreToolUse"
	e.HookSpecificOutput.PermissionDecision = "allow"
	e.HookSpecificOutput.UpdatedInput = &updatedInput{Command: command}
	b, _ := sonic.Marshal(e)
	_, _ = w.Write(b)
}
