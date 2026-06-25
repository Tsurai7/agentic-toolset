// Command agentic is the cross-platform CLI for the agentic-cfg toolset.
//
// It is being introduced incrementally (P1; see plans/01-go-rewrite.md): each
// subcommand replaces a piece of the shell/Python install + hook glue with a
// single static binary that does real JSON handling and is unit-testable.
package main

import (
	"fmt"
	"os"

	"github.com/Tsurai7/agentic-cfg/internal/hook"
	"github.com/Tsurai7/agentic-cfg/internal/settings"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	switch os.Args[1] {
	case "hook":
		os.Exit(hook.Main(os.Args[2:]))
	case "merge-settings":
		os.Exit(mergeSettings(os.Args[2:]))
	case "-h", "--help", "help":
		usage()
		os.Exit(0)
	default:
		fmt.Fprintf(os.Stderr, "agentic: unknown command %q\n\n", os.Args[1])
		usage()
		os.Exit(2)
	}
}

func mergeSettings(args []string) int {
	if len(args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: agentic merge-settings <fragment.json> <output settings.json>")
		return 1
	}
	if err := settings.Merge(args[0], args[1]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

func usage() {
	fmt.Fprint(os.Stderr, `usage: agentic <command> [args]

commands:
  hook shell-guard                      PreToolUse Bash hook (shell + code-search precedence)
  merge-settings <fragment> <out>       merge hooks + permissions into a settings.json
`)
}
