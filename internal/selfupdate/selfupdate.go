// Package selfupdate implements `agentic update` and `agentic version`: pulling
// the agentic-cfg checkout forward (git pull --ff-only), re-running the
// installer so the update is applied to every provider, and reporting what
// version a checkout is on.
//
// Plain functions, io.Writer injection for output, no globals, stdlib only —
// mirrors the conventions of the sibling internal/gain and internal/hook
// packages.
package selfupdate

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// validateRoot returns an error unless root looks like an agentic-cfg checkout
// (has .git and bin/install.sh).
func validateRoot(root string) error {
	if _, err := os.Stat(filepath.Join(root, ".git")); err != nil {
		return fmt.Errorf("not an agentic-cfg checkout: %s has no .git", root)
	}
	if _, err := os.Stat(filepath.Join(root, "bin", "install.sh")); err != nil {
		return fmt.Errorf("not an agentic-cfg checkout: %s has no bin/install.sh", root)
	}
	return nil
}

// describe returns `git describe --tags --always --dirty` for root, falling
// back to the short HEAD hash on any git error. Never panics.
func describe(root string) string {
	out, err := exec.Command("git", "-C", root, "describe", "--tags", "--always", "--dirty").Output() //nolint:noctx // one-shot synchronous subprocess; no cancellation context flows through this CLI path
	if err == nil {
		if s := strings.TrimSpace(string(out)); s != "" {
			return s
		}
	}
	out, err = exec.Command("git", "-C", root, "rev-parse", "--short", "HEAD").Output() //nolint:noctx // one-shot synchronous subprocess; no cancellation context flows through this CLI path
	if err == nil {
		if s := strings.TrimSpace(string(out)); s != "" {
			return s
		}
	}
	return "unknown"
}

// Update pulls root's checkout forward (ff-only) and re-applies the config to
// every provider, streaming git/installer output to w as it runs. On a
// non-zero exit from either step, the returned error includes that step's own
// output verbatim (a diverged branch or a conflicting dirty file must surface
// exactly as git reported it, not be rephrased).
func Update(w io.Writer, root string) error {
	if err := validateRoot(root); err != nil {
		return err
	}
	before := describe(root)

	pull := exec.Command("git", "-C", root, "pull", "--ff-only") //nolint:noctx // one-shot synchronous subprocess; no cancellation context flows through this CLI path
	pullOut, err := pull.CombinedOutput()
	_, _ = w.Write(pullOut)
	if err != nil {
		return fmt.Errorf("git pull --ff-only: %w\n%s", err, pullOut)
	}
	alreadyUpToDate := strings.Contains(string(pullOut), "Already up to date")

	install := exec.Command("bash", "bin/install.sh", "--provider", "all") //nolint:noctx // one-shot synchronous subprocess; no cancellation context flows through this CLI path
	install.Dir = root
	installOut, err := install.CombinedOutput()
	_, _ = w.Write(installOut)
	if err != nil {
		return fmt.Errorf("bin/install.sh --provider all: %w\n%s", err, installOut)
	}

	after := describe(root)
	if alreadyUpToDate {
		fmt.Fprintf(w, "agentic-cfg already up to date (%s); config re-applied.\n", after)
	} else {
		fmt.Fprintf(w, "agentic-cfg updated: %s -> %s\n", before, after)
	}
	fmt.Fprintln(w, "note: running Claude/Cursor sessions keep the prefix they started with; new sessions pick up the update.")
	return nil
}

// Version prints the checkout's version (git describe) and root to w. Errors
// if root/.git is missing.
func Version(w io.Writer, root string) error {
	if _, err := os.Stat(filepath.Join(root, ".git")); err != nil {
		return fmt.Errorf("not an agentic-cfg checkout: %s has no .git", root)
	}
	commitDate, err := exec.Command("git", "-C", root, "log", "-1", "--format=%cs").Output() //nolint:noctx // one-shot synchronous subprocess; no cancellation context flows through this CLI path
	if err != nil {
		return fmt.Errorf("git log: %w", err)
	}
	shortHead, err := exec.Command("git", "-C", root, "rev-parse", "--short", "HEAD").Output() //nolint:noctx // one-shot synchronous subprocess; no cancellation context flows through this CLI path
	if err != nil {
		return fmt.Errorf("git rev-parse: %w", err)
	}
	fmt.Fprintf(w, "agentic-cfg %s  (commit %s, %s)\n",
		describe(root), strings.TrimSpace(string(shortHead)), strings.TrimSpace(string(commitDate)))
	fmt.Fprintf(w, "root: %s\n", root)
	return nil
}
