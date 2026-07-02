# Office-hours: split agentic-cfg into multiple repos?

> Method: the in-repo [`office-hours`](../../core/skills/office-hours/SKILL.md) skill —
> "should we adopt X?" routing ⇒ all six forcing questions. Session 2026-07-02.
> The ask (user): *"есть ли смысл разнести его по разным репозиториям, по типу
> agentic-principles, agentic-toolset и т.д."*

## Q1 — Premise challenge

Restated: "the toolset now spans principles, skills, agent roles, hooks, a Go CLI,
evals, and docs — should each concern get its own repository?" Repo count is a
mechanism, not a goal. The underlying wants are (a) a clear mental model of the
parts, (b) selective reuse of a part without the whole, (c) small blast radius per
change. All three can be served either by repo boundaries or by in-repo boundaries
plus gates. Reframed question we actually answer: **which boundaries are load-bearing,
and is any of them better enforced by a separate repository today?**

## Q2 — Status quo

The repo is already modular where it matters, and the one seam that earns separate
repos is already cut:

- **Runtime tools are external repos** (lean-ctx, gitnexus, rtk, no-mistakes);
  `integrations/` only wires them, `catalog/plugins.yaml` catalogs marketplace
  plugins and explicitly forbids vendoring.
- **Inside, boundaries are directories with CI-enforced contracts**: skill ↔ eval
  pairing (`evals/lint.py` fails a skill with no case), the always-on byte budget
  (`bin/prefix-budget.sh` spans instructions + principles + user-rules), Go ↔ Python
  merge parity suites, `bin/ci-check.sh` over everything.
- **Portability is by render, not by source sharing**: `core/instructions/AGENTS.md`
  is designed to be dropped into other projects as-is; providers consume rendered
  artifacts (`agentic-cfg.generated.md`, symlinks), never the tree.

Genuinely missing: a low-friction way for a *second consumer* to take a subset
(say, principles + instructions) without cloning everything. No such consumer
exists today.

## Q3 — Evidence of value

Who benefits from a split, and what number moves? Measured state (2026-07-02):
private repo, **0 forks, 0 stars** — one maintainer, one machine class; 228 tracked
files, ~5 MB of git history (the only heavy thing in the working tree is a local,
untracked GitNexus index); full local gate battery ≈ 3–4 min, CI run 38 s–1 m.
Candidate benefits examined:

| Claimed benefit | Reality here |
|---|---|
| Smaller clones / faster CI | Already trivial (a few-MB clone, ~1 min CI); a split saves seconds and adds repo-hop minutes |
| Independent versioning | No consumer needs any part at a different version than the whole |
| Reuse by others | Zero external consumers today; when one appears, a rendered artifact serves them better than a source split (Q4) |
| Cleaner mental model | Solved by documentation — [`docs/HOW-IT-WORKS.md`](../HOW-IT-WORKS.md) (this session) |

No measurable number improves from a split today. Two numbers get worse:
wave latency (today's improvement wave touched core+providers+internal+evals in one
PR, one CI run, one merge — across 3–4 repos that becomes coordinated releases with
version pins) and enforcement coverage (the skill↔eval and byte-budget gates cannot
span repos without new pinning machinery that does not exist).

## Q4 — Narrowest wedge

The smallest thing that serves the underlying wants, shippable now:

1. **The map, not the split**: `docs/HOW-IT-WORKS.md` (landed with this session)
   gives the component-by-component mental model.
2. **When (if) a second consumer appears**: publish a **rendered baseline
   artifact** from this source — e.g. a CI job that emits `AGENTS.md` + principles
   as a template repo or a marketplace plugin (`agentic-baseline`). ~50 lines of CI,
   zero source movement, consumers pin a release tag.

Explicitly out of scope: moving any `core/**` source out; git submodules/subtrees;
a meta-repo; splitting evals from the content they gate.

## Q5 — Risk & verification

Blast radius of an actual split: severs `evals/lint.py`'s skill↔eval pairing gate,
splits `bin/prefix-budget.sh`'s scope across repos (a byte added in one must be
paid by a trim in another), breaks the installer's single-root model
(`__AGENTIC_ROOT__` resolution, symlink targets), and multiplies release process.
No existing gate proves a split-world install correct — that machinery would have
to be built first. Keeping the monorepo needs no new verification: `bin/ci-check.sh`
already vouches for the whole surface per commit.

## Q6 — Cost of keeping (the monorepo)

Ongoing cost of not splitting: none material at this scale (navigation is solved by
docs; CI is ~1 min; the tracked tree is a few MB). Revisit triggers — any one of
these reopens the question:

1. A real second consumer wants principles/instructions (→ ship the Q4 rendered
   artifact first; split only if the artifact proves insufficient).
2. Team adoption where write-access boundaries between parts matter.
3. The eval harness generalizes into a standalone product with outside users — it
   is the one component with a clean enough interface to extract.
4. Scale pain: CI > 10 min or a clone that hurts.

## Verdict

**Do not split.** The seam that deserves separate repositories — runtime tools vs
the config that wires them — is already cut and already respected. Every proposed
internal split (principles / toolset / evals) would sever a CI-enforced contract
that is the repo's actual quality mechanism, to obtain benefits (size, versioning,
reuse) that measure at zero here. Narrowest wedge for the real wants: the
`HOW-IT-WORKS.md` map now; a CI-generated rendered baseline artifact if a second
consumer ever materializes.
