# self-update — wave index

`agentic-cfg update` + versioning. Rationale and scope: [DESIGN.md](DESIGN.md)
(public repo **not** required — update works on the existing clone with the user's
own credentials).

## Plans and status

| # | Plan | Files touched | Status |
|---|------|---------------|--------|
| 01 | [update + version subcommands](01-update-version-commands.md) | `internal/selfupdate/selfupdate.go` (new), `internal/selfupdate/selfupdate_test.go` (new), `cmd/agentic/main.go` | done |
| 02 | [install auto-link, doctor PATH check, docs](02-install-link-doctor-docs.md) | `bin/install.sh`, `bin/doctor.sh`, `SETUP.md`, `CHANGELOG.md` | done |

## Execution order

- 01 and 02 in parallel — file sets are disjoint.
- **Verify:** gates below + per-plan ACs against the actual diff, by a verifier that
  changes nothing.

## Verification gates (all must pass before merge)

```bash
go test ./... -count=1
bash bin/ci-check.sh
python3 evals/lint.py        # 22 cases, 10 skills covered — unchanged
bash bin/prefix-budget.sh    # 8754 bytes — unchanged
```

Machine-side E2E (implementing machine, after the diff):

```bash
bash bin/install.sh --provider all   # now ends with the auto-link step
command -v agentic-cfg               # ~/.local/bin/agentic-cfg
agentic-cfg version                  # describe/hash + commit date + root
agentic-cfg update                   # already-up-to-date path: pull + rebuild + re-apply
                                     # (run post-merge on master — a feature branch
                                     #  without upstream has nothing to pull)
bash bin/doctor.sh                   # includes the PATH-link OK line
```

## Post-merge step (orchestrator)

Tag the merge commit `v0.15.0` (aligned with the CHANGELOG entry) and push the tag —
from then on `agentic-cfg version` / `update` report `git describe` versions.

## Deferred follow-ups

- README quickstart line for `agentic-cfg update` — README carries foreign
  uncommitted changes from a concurrent session; add once the tree clears.
- Fresh-machine bootstrap story (clone+install one-liner) — only if a second machine
  actually materializes; would re-open the public-repo question.
