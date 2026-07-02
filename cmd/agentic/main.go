// Command agentic is the cross-platform CLI for the agentic-cfg toolset.
//
// It is being introduced incrementally (P1; see plans/01-go-rewrite.md): each
// subcommand replaces a piece of the shell/Python install + hook glue with a
// single static binary that does real JSON handling and is unit-testable.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/Tsurai7/agentic-cfg/internal/claudemd"
	"github.com/Tsurai7/agentic-cfg/internal/gain"
	"github.com/Tsurai7/agentic-cfg/internal/hook"
	"github.com/Tsurai7/agentic-cfg/internal/lifecycle"
	"github.com/Tsurai7/agentic-cfg/internal/mcpmerge"
	"github.com/Tsurai7/agentic-cfg/internal/selfupdate"
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
	case "cache":
		// Discoverable alias for the cache-focused gain view.
		return gain.Main(append([]string{"--cache"}, args[1:]...))
	case "inject":
		return injectEject("inject", args[1:])
	case "eject":
		return injectEject("eject", args[1:])
	case "status":
		return statusCmd(args[1:])
	case "link":
		return linkCmd(args[1:])
	case "update":
		return updateCmd(args[1:])
	case "version":
		return versionCmd(args[1:])
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

func statusCmd(args []string) int {
	fs := flag.NewFlagSet("status", flag.ContinueOnError)
	root := fs.String("root", defaultRoot(), "agentic-cfg repo root")
	home := fs.String("home", "", "target home dir (default: $HOME)")
	asJSON := fs.Bool("json", false, "emit JSON instead of a table")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	h := *home
	if h == "" {
		var err error
		if h, err = os.UserHomeDir(); err != nil {
			fmt.Fprintf(os.Stderr, "agentic status: cannot resolve home: %v\n", err)
			return 1
		}
	}
	rep := lifecycle.Status(lifecycle.Options{Root: *root, Home: h})
	if *asJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		_ = enc.Encode(rep)
	} else {
		rep.Render(os.Stdout, h)
	}
	if rep.Injected { // exit 1 when not (fully) injected — handy for scripts
		return 0
	}
	return 1
}

func updateCmd(args []string) int {
	fs := flag.NewFlagSet("update", flag.ContinueOnError)
	root := fs.String("root", defaultRoot(), "agentic-cfg repo root")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if err := selfupdate.Update(os.Stdout, *root); err != nil {
		fmt.Fprintf(os.Stderr, "agentic update: %v\n", err)
		return 1
	}
	return 0
}

func versionCmd(args []string) int {
	fs := flag.NewFlagSet("version", flag.ContinueOnError)
	root := fs.String("root", defaultRoot(), "agentic-cfg repo root")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if err := selfupdate.Version(os.Stdout, *root); err != nil {
		fmt.Fprintf(os.Stderr, "agentic version: %v\n", err)
		return 1
	}
	return 0
}

// defaultRoot derives the repo root from the running binary (repo/bin/agentic ->
// repo). Falls back to the current directory.
func defaultRoot() string {
	if exe, err := os.Executable(); err == nil {
		// Resolve symlinks so a binary linked onto PATH (agentic link) still
		// resolves back to repo/bin/agentic -> repo.
		if resolved, err := filepath.EvalSymlinks(exe); err == nil {
			exe = resolved
		}
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

// linkCmd symlinks `agentic` and `agentic-cfg` into a PATH directory so they can
// be run from anywhere.
func linkCmd(args []string) int {
	fs := flag.NewFlagSet("link", flag.ContinueOnError)
	dir := fs.String("dir", defaultBinDir(), "directory (on your PATH) to link the commands into")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	exe, err := os.Executable()
	if err != nil {
		fmt.Fprintf(os.Stderr, "agentic link: %v\n", err)
		return 1
	}
	if resolved, e := filepath.EvalSymlinks(exe); e == nil {
		exe = resolved
	}
	created, skipped, err := linkInto(exe, *dir, []string{"agentic", "agentic-cfg"})
	if err != nil {
		fmt.Fprintf(os.Stderr, "agentic link: %v\n", err)
		return 1
	}
	for _, c := range created {
		fmt.Printf("linked %s -> %s\n", c, exe)
	}
	for _, s := range skipped {
		fmt.Printf("skipped %s (exists and is not our symlink — remove it first)\n", s)
	}
	if !dirOnPath(*dir) {
		fmt.Printf("note: %s is not on your PATH. Add it, e.g.:\n  echo 'export PATH=\"%s:$PATH\"' >> ~/.zshrc\n", *dir, *dir)
	}
	return 0
}

// linkInto symlinks exe into dir under each name. An existing matching symlink is
// left in place (idempotent); a stale symlink is replaced; a real file is skipped
// (never clobbered).
func linkInto(exe, dir string, names []string) (created, skipped []string, err error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, nil, err
	}
	for _, name := range names {
		target := filepath.Join(dir, name)
		if fi, e := os.Lstat(target); e == nil {
			if fi.Mode()&os.ModeSymlink == 0 {
				skipped = append(skipped, target) // a real file — don't clobber
				continue
			}
			if dest, _ := os.Readlink(target); dest != exe {
				_ = os.Remove(target) // replace a stale/other symlink
			}
		}
		if e := os.Symlink(exe, target); e != nil && !os.IsExist(e) {
			return created, skipped, e
		}
		created = append(created, target)
	}
	return created, skipped, nil
}

func defaultBinDir() string {
	if h, err := os.UserHomeDir(); err == nil {
		return filepath.Join(h, ".local", "bin")
	}
	return "/usr/local/bin"
}

func dirOnPath(dir string) bool {
	for _, p := range filepath.SplitList(os.Getenv("PATH")) {
		if p == dir {
			return true
		}
	}
	return false
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
  cache [--last N] [--by-model] [--json]    cache-focused readout: prompt-cache hit rate + cost saved
  inject [--root DIR] [--home DIR] [--dry-run]   add the agentic-cfg footprint to a Claude config
  eject  [--root DIR] [--home DIR] [--dry-run]   cleanly remove it (preserves your own content)
  status [--root DIR] [--home DIR] [--json]      report whether agentic-cfg is injected
  link   [--dir DIR]                             symlink agentic + agentic-cfg onto your PATH (~/.local/bin)
  update [--root DIR]                            pull latest (ff-only), rebuild, re-apply to all providers
  version [--root DIR]                           show checkout version (git describe) and repo root
`)
}
