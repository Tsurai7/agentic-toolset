package selfupdate

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// runGit runs git in dir and fails the test on error, returning combined output.
func runGit(t *testing.T, dir string, args ...string) string {
	t.Helper()
	cmd := exec.Command("git", append([]string{"-C", dir}, args...)...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("git -C %s %s: %v\n%s", dir, strings.Join(args, " "), err, out)
	}
	return string(out)
}

// initCheckout creates a bare "origin" repo plus one clone of it at dir, with an
// initial commit containing a bin/install.sh stub that records its args into
// install-args.txt and prints "STUB INSTALL". Returns the origin's bare path and
// the default branch name (never assumed to be "master").
func initCheckout(t *testing.T, base, dir string) (originBare, branch string) {
	t.Helper()
	src := filepath.Join(base, "origin-src")
	if err := os.MkdirAll(filepath.Join(src, "bin"), 0o755); err != nil {
		t.Fatal(err)
	}
	stub := "#!/bin/bash\necho \"$@\" > install-args.txt\necho STUB INSTALL\n"
	if err := os.WriteFile(filepath.Join(src, "bin", "install.sh"), []byte(stub), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(src, "README.md"), []byte("hello\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	runGit(t, src, "init", "-q")
	runGit(t, src, "config", "user.name", "Test")
	runGit(t, src, "config", "user.email", "test@example.com")
	runGit(t, src, "add", "-A")
	runGit(t, src, "commit", "-q", "-m", "initial")
	branch = strings.TrimSpace(runGit(t, src, "symbolic-ref", "--short", "HEAD"))

	originBare = filepath.Join(base, "origin.git")
	cmd := exec.Command("git", "clone", "-q", "--bare", src, originBare)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("git clone --bare: %v\n%s", err, out)
	}

	cmd = exec.Command("git", "clone", "-q", originBare, dir)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("git clone %s %s: %v\n%s", originBare, dir, err, out)
	}
	runGit(t, dir, "config", "user.name", "Test")
	runGit(t, dir, "config", "user.email", "test@example.com")
	return originBare, branch
}

// pushOriginCommit clones originBare into a scratch dir, adds a commit, and
// pushes it, simulating another machine advancing origin.
func pushOriginCommit(t *testing.T, base, originBare, branch, message string) {
	t.Helper()
	scratch := filepath.Join(base, "scratch-"+message)
	cmd := exec.Command("git", "clone", "-q", originBare, scratch)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("git clone %s: %v\n%s", originBare, err, out)
	}
	runGit(t, scratch, "config", "user.name", "Test")
	runGit(t, scratch, "config", "user.email", "test@example.com")
	f := filepath.Join(scratch, "README.md")
	b, err := os.ReadFile(f)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(f, append(b, []byte(message+"\n")...), 0o644); err != nil {
		t.Fatal(err)
	}
	runGit(t, scratch, "commit", "-q", "-am", message)
	runGit(t, scratch, "push", "-q", "origin", branch)
}

func TestVersionTaggedAndUntagged(t *testing.T) {
	base := t.TempDir()
	dir := filepath.Join(base, "clone")
	initCheckout(t, base, dir)

	var buf bytes.Buffer
	if err := Version(&buf, dir); err != nil {
		t.Fatalf("Version: %v", err)
	}
	shortHead := strings.TrimSpace(runGit(t, dir, "rev-parse", "--short", "HEAD"))
	if !strings.Contains(buf.String(), shortHead) {
		t.Errorf("untagged output %q does not contain short hash %q", buf.String(), shortHead)
	}
	if !strings.Contains(buf.String(), "root: "+dir) {
		t.Errorf("untagged output %q does not contain root: %s", buf.String(), dir)
	}

	runGit(t, dir, "tag", "v9.9.9")
	buf.Reset()
	if err := Version(&buf, dir); err != nil {
		t.Fatalf("Version after tag: %v", err)
	}
	if !strings.Contains(buf.String(), "v9.9.9") {
		t.Errorf("tagged output %q does not contain v9.9.9", buf.String())
	}
	if !strings.Contains(buf.String(), "root: "+dir) {
		t.Errorf("tagged output %q does not contain root: %s", buf.String(), dir)
	}
}

func TestUpdateFastForwards(t *testing.T) {
	base := t.TempDir()
	dir := filepath.Join(base, "clone")
	originBare, branch := initCheckout(t, base, dir)
	pushOriginCommit(t, base, originBare, branch, "second-commit")

	var buf bytes.Buffer
	if err := Update(&buf, dir); err != nil {
		t.Fatalf("Update: %v\noutput:\n%s", err, buf.String())
	}

	head := strings.TrimSpace(runGit(t, dir, "rev-parse", "HEAD"))
	originHead := strings.TrimSpace(runGit(t, originBare, "rev-parse", branch))
	if head != originHead {
		t.Errorf("HEAD = %s, want origin HEAD %s", head, originHead)
	}
	argsPath := filepath.Join(dir, "install-args.txt")
	argsBytes, err := os.ReadFile(argsPath)
	if err != nil {
		t.Fatalf("install-args.txt not written: %v", err)
	}
	if !strings.Contains(string(argsBytes), "--provider all") {
		t.Errorf("install-args.txt = %q, want it to contain --provider all", argsBytes)
	}
	if !strings.Contains(buf.String(), "->") {
		t.Errorf("summary output %q does not contain '->'", buf.String())
	}
}

func TestUpdateAlreadyUpToDate(t *testing.T) {
	base := t.TempDir()
	dir := filepath.Join(base, "clone")
	initCheckout(t, base, dir)

	var buf bytes.Buffer
	if err := Update(&buf, dir); err != nil {
		t.Fatalf("Update: %v\noutput:\n%s", err, buf.String())
	}
	if !strings.Contains(buf.String(), "already up to date") {
		t.Errorf("summary output %q does not contain 'already up to date'", buf.String())
	}
	if _, err := os.Stat(filepath.Join(dir, "install-args.txt")); err != nil {
		t.Errorf("install-args.txt not written: %v", err)
	}
}

func TestUpdateRefusesDiverged(t *testing.T) {
	base := t.TempDir()
	dir := filepath.Join(base, "clone")
	originBare, branch := initCheckout(t, base, dir)
	pushOriginCommit(t, base, originBare, branch, "origin-side-commit")

	// Diverge dir with its own local commit.
	f := filepath.Join(dir, "README.md")
	b, err := os.ReadFile(f)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(f, append(b, []byte("local-change\n")...), 0o644); err != nil {
		t.Fatal(err)
	}
	runGit(t, dir, "commit", "-q", "-am", "local commit")
	localHead := strings.TrimSpace(runGit(t, dir, "rev-parse", "HEAD"))

	var buf bytes.Buffer
	err = Update(&buf, dir)
	if err == nil {
		t.Fatal("Update: want error on diverged branch, got nil")
	}
	if !strings.Contains(err.Error(), "fast-forward") {
		t.Errorf("error %q does not include git's ff-only refusal text", err.Error())
	}

	headAfter := strings.TrimSpace(runGit(t, dir, "rev-parse", "HEAD"))
	if headAfter != localHead {
		t.Errorf("HEAD changed after failed pull: got %s, want unchanged %s", headAfter, localHead)
	}
	if _, statErr := os.Stat(filepath.Join(dir, "install-args.txt")); statErr == nil {
		t.Error("install-args.txt was written, want stub installer to NOT have run")
	}
}

func TestUpdateRejectsNonCheckout(t *testing.T) {
	dir := t.TempDir()
	var buf bytes.Buffer
	err := Update(&buf, dir)
	if err == nil {
		t.Fatal("Update: want error for a non-checkout dir, got nil")
	}
	if !strings.Contains(err.Error(), "not an agentic-cfg checkout") {
		t.Errorf("error %q does not mention 'not an agentic-cfg checkout'", err.Error())
	}
}
