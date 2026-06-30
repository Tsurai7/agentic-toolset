// Command agentic is the cross-platform CLI for the agentic-cfg toolset.
//
// It is being introduced incrementally (P1; see plans/01-go-rewrite.md): each
// subcommand replaces a piece of the shell/Python install + hook glue with a
// single static binary that does real JSON handling and is unit-testable.
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/Tsurai7/agentic-cfg/internal/claudemd"
	"github.com/Tsurai7/agentic-cfg/internal/gain"
	"github.com/Tsurai7/agentic-cfg/internal/hook"
	"github.com/Tsurai7/agentic-cfg/internal/lifecycle"
	"github.com/Tsurai7/agentic-cfg/internal/mcpmerge"
	"github.com/Tsurai7/agentic-cfg/internal/settings"
)

func main() { os.Exit(run(os.Args[1:])) }

// run dispatches a subcommand and returns the process exit code. Split out from
// main (which only adds os.Exit) so the CLI surface — including `inject`/`eject`,
// invoked as either `agentic` or `agentic-cfg` — is unit-testable end to end.
func run(args []string) int {
	if len(args) < 1 {
		usage()
		return 2
	}
	switch args[0] {
	case "hook":
		return hook.Main(args[1:])
	case "merge-settings":
		return mergeSettings(args[1:])
	case "merge-mcp":
		return mergeMCP(args[1:])
	case "merge-claude-md":
		return mergeClaudeMD(args[1:])
	case "gain":
		return gain.Main(args[1:])
	case "inject":
		return injectEject("inject", args[1:])
	case "eject":
		return injectEject("eject", args[1:])
	case "-h", "--help", "help":
		usage()
		return 0
	default:
		fmt.Fprintf(os.Stderr, "agentic: unknown command %q\n\n", args[0])
		usage()
		return 2
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

func mergeMCP(args []string) int {
	if len(args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: agentic merge-mcp <agentic_root> <output_mcp.json | --register-claude-user>")
		return 1
	}
	root := args[0]
	var err error
	if args[1] == "--register-claude-user" {
		err = mcpmerge.RegisterClaudeUser(root)
	} else {
		err = mcpmerge.MergeCursor(root, args[1])
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

func mergeClaudeMD(args []string) int {
	if len(args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: agentic merge-claude-md <generated_file> <claude_md>")
		return 1
	}
	if err := claudemd.Ensure(args[0], args[1]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

func injectEject(action string, args []string) int {
	fs := flag.NewFlagSet(action, flag.ContinueOnError)
	root := fs.String("root", defaultRoot(), "agentic-cfg repo root (default: derived from the binary location)")
	home := fs.String("home", "", "target home dir (default: $HOME)")
	dryRun := fs.Bool("dry-run", false, "print actions without changing anything")
	skipMCP := fs.Bool("skip-mcp", false, "skip the MCP step (the `claude` CLI is global, not --home-scoped)")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	h := *home
	if h == "" {
		var err error
		if h, err = os.UserHomeDir(); err != nil {
			fmt.Fprintf(os.Stderr, "agentic %s: cannot resolve home: %v\n", action, err)
			return 1
		}
	}
	opts := lifecycle.Options{Root: *root, Home: h, DryRun: *dryRun, SkipMCP: *skipMCP}
	var err error
	if action == "inject" {
		err = lifecycle.Inject(opts)
	} else {
		err = lifecycle.Eject(opts)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "agentic %s: %v\n", action, err)
		return 1
	}
	return 0
}

// defaultRoot derives the repo root from the running binary (repo/bin/agentic ->
// repo). Falls back to the current directory.
func defaultRoot() string {
	exe, err := os.Executable()
	if err == nil {
		if root := filepath.Dir(filepath.Dir(exe)); root != "" {
			if _, err := os.Stat(filepath.Join(root, "core", "skills")); err == nil {
				return root
			}
		}
	}
	if wd, err := os.Getwd(); err == nil {
		return wd
	}
	return "."
}

func usage() {
	fmt.Fprint(os.Stderr, `usage: agentic <command> [args]

commands:
  hook shell-guard                          PreToolUse Bash hook (shell + code-search precedence)
  merge-settings <fragment> <out>           merge hooks + permissions into a settings.json
  merge-mcp <root> <out>                    merge managed MCP servers into a mcp.json (Cursor)
  merge-mcp <root> --register-claude-user   register managed MCP servers at Claude user scope
  merge-claude-md <generated> <claude_md>   ensure CLAUDE.md @imports the generated config
  gain [--last N] [--project S] [--json]    performance readout: token volume, cache hit rate, cost saved
  inject [--root DIR] [--home DIR] [--dry-run]   add the agentic-cfg footprint to a Claude config
  eject  [--root DIR] [--home DIR] [--dry-run]   cleanly remove it (preserves your own content)
`)
}
