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
	"encoding/json"
	"io"
	"os"
	"os/exec"
	"regexp"
	"strings"
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
	grepTokenRe     = regexp.MustCompile(`(^|[|&;]| )(grep|egrep|fgrep|rg)( |$)`)
	leadingAssignRe = regexp.MustCompile(`^\s*[A-Za-z_][A-Za-z0-9_]*=`)
	assignTokenRe   = regexp.MustCompile(`^\s*[A-Za-z_][A-Za-z0-9_]*=\S*\s+`)
	quotedRe        = regexp.MustCompile(`'[^']*'|"[^"]*"`)
)

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

func shellGuard(stdin io.Reader, stdout io.Writer) int {
	raw, err := io.ReadAll(stdin)
	if err != nil {
		return 0
	}
	var in hookInput
	if err := json.Unmarshal(raw, &in); err != nil {
		return 0 // unparseable input: fail open
	}
	switch in.ToolName {
	case "Bash", "bash", "PowerShell", "powershell":
	default:
		return 0
	}
	cmd := in.ToolInput.Command
	if strings.TrimSpace(cmd) == "" {
		return 0
	}

	// Already wrapped (after stripping any leading VAR= assignments).
	if w := stripLeadingAssignments(cmd); strings.HasPrefix(w, "rtk ") || strings.HasPrefix(w, "lean-ctx ") {
		return 0
	}

	// Complex commands a wrapper would mangle -> fail open (run untouched).
	if strings.Contains(cmd, "<<") || strings.Contains(cmd, "\n") ||
		strings.Contains(cmd, "$(") || strings.Contains(cmd, "`") ||
		strings.HasPrefix(cmd, "cd ") || strings.Contains(cmd, "&& cd ") || strings.Contains(cmd, "; cd ") {
		return 0
	}

	// 1. ast-grep guard: deny only when grep/rg targets a code FILE. A code
	// extension inside a quoted search pattern is ignored.
	if grepTokenRe.MatchString(cmd) && codeExtRe.MatchString(quotedRe.ReplaceAllString(cmd, "")) {
		writeDeny(stdout)
		return 0
	}

	// 2. lean-ctx delegate (it safely wraps a whole command).
	if out, ok := leanCtxRewrite(raw); ok {
		_, _ = stdout.Write(out)
		return 0
	}

	// 3. rtk fallback for simple commands. A leading assignment would be lost by
	// a naive prefix, so pass it through untouched instead.
	if !hasRTK() {
		return 0
	}
	if leadingAssignRe.MatchString(cmd) {
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
	b, _ := json.Marshal(e)
	_, _ = w.Write(b)
}

func writeRewrite(w io.Writer, command string) {
	var e decisionEnvelope
	e.HookSpecificOutput.HookEventName = "PreToolUse"
	e.HookSpecificOutput.PermissionDecision = "allow"
	e.HookSpecificOutput.UpdatedInput = &updatedInput{Command: command}
	b, _ := json.Marshal(e)
	_, _ = w.Write(b)
}
