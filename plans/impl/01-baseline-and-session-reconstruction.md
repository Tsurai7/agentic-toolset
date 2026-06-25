# Impl 01 — Baseline corpus capture, session reconstruction, and the corrected cost unit

- **Status:** Not started (Wave 0 — must land before the P0 install)
- **ADR:** [ADR-0001](../adr/0001-real-usage-measurement-baseline.md)
- **Related impl:** feeds [`plans/impl/02-quality-latency-proxies.md`](02-quality-latency-proxies.md) (proxies read the reconstructed corpus), [`plans/impl/04-gain-scorecard-experiment.md`](04-gain-scorecard-experiment.md) (scorecard reads the corrected units), [`plans/impl/05-model-tiering-routing.md`](05-model-tiering-routing.md) (routing KPI = corrected Opus share).
- **Read-only references:** [`plans/00-master-plan.md`](../00-master-plan.md) P0 install steps; the P0 hook/install items BUG-01..23, PORT-01..12 land *after* this.

## Scope and deliverables

This plan instruments the harness *before* anything is installed, so every later number is attributable. It delivers four things, all stdlib and zero-token, matching the existing [`telemetry/report.py`](../../telemetry/report.py) constraint:

1. **`telemetry/snapshot.py`** (new) — freeze the pre-install real-session corpus into a gitignored, append-only `telemetry/baseline/<date>-<sha>/`, tagged with capture date and repo SHA.
2. **Logical session reconstruction** in `telemetry/report.py:collect()` — group subagent (`isSidechain`, `.../subagents/...`) transcript files under their parent session so `--last N` windows real sessions, not raw files.
3. **The corrected cost unit** — a sidechain-excluded, `<synthetic>`-filtered, tier-normalized `main_thread_opus_input_token_share` as the headline KPI, with `$est` relabeled "API-equivalent proxy (not the owner's bill)."
4. **A `--baseline <dir>` diff mode** on `report.py` and `gate.py` that diffs the live window against the frozen corpus per metric, plus a [`telemetry/INTEGRATION.md`](../../telemetry/INTEGRATION.md) section wiring this into the program.

Out of scope (owned elsewhere, referenced read-only): the quality/latency proxy parsers ([impl 02](02-quality-latency-proxies.md)), the eval/canary backbone ([impl 03](03-eval-backbone-canary.md)), the scorecard aggregator ([impl 04](04-gain-scorecard-experiment.md)), and the routing rule content ([impl 05](05-model-tiering-routing.md)). This plan only produces the *correct corpus and units* they all consume.

## File-by-file changes

### A. New file: `telemetry/snapshot.py`

A read-only freezer. It copies the current `~/.claude/projects/**/*.jsonl` into an immutable, gitignored corpus directory tagged with date and repo SHA, and writes a small manifest so later diffs can cite exactly what was frozen.

```python
# telemetry/snapshot.py  (stdlib only, read-only on ~/.claude)
# Freeze the pre-install real-session corpus so every before/after delta is attributable.
def repo_sha() -> str:
    # subprocess git rev-parse --short HEAD in the agentic-cfg checkout; "nogit" fallback
def snapshot(src=~/.claude/projects, dest=telemetry/baseline) -> Path:
    tag = f"{date.today().isoformat()}-{repo_sha()}"
    out = dest / tag
    if out.exists():                       # append-only: never mutate a frozen corpus
        raise SystemExit(f"baseline {tag} already exists; refusing to overwrite")
    for f in src.glob("**/*.jsonl"):
        copy preserving the subagents/ subpath so reconstruction still works
    write out/manifest.json = {tag, captured_at, repo_sha, file_count, src_root, note}
    print frozen file_count + path
# CLI: python3 telemetry/snapshot.py [--src ...] [--dest telemetry/baseline] [--note "pre-P0"]
```

The corpus preserves the relative subpath (so `.../subagents/...` survives) because session reconstruction (change B) keys on it. The manifest's `repo_sha` is the immutability anchor the ADR's Validation step 1 cites.

### B. `telemetry/report.py:collect()` (`report.py:179-189`) — logical session reconstruction

Today `collect()` sorts `**/*.jsonl` by mtime and returns one `SessionStats` per *file*. Subagent transcripts are separate files under `.../subagents/...`, so a fanned-out task becomes many "sessions" and `--last N` windows files, not tasks (critique P0-2). Reconstruct logical sessions by grouping child files under their parent before applying the window.

```python
def _parent_key(path, st):
    # sidechain / subagent files group under their parent. Prefer st.session_id /
    # workflow root if present in the record; else the subagents/ parent dir.
    if "subagents" in path.parts:
        return path.parts[path.parts.index("subagents") - 1]   # the parent session dir
    return st.session_id or path.stem

def collect(root, project, baseline=None):
    files = sorted(root.glob("**/*.jsonl"), key=mtime, reverse=True)
    groups: dict[str, list[SessionStats]] = group parsed files by _parent_key
    sessions = [merge(group) for group in groups]   # merge child stats into the parent
    sessions.sort(by most-recent last_ts, reverse=True)
    apply project filter, return sessions
```

`merge(group)` folds child token buckets into the parent's `tokens["sub"]` and unions `tools`/`models`, so a reconstructed session carries the *whole* workflow. The `--last N` slice in `main()` (`report.py:295`) and `gate.py:main()` (`gate.py:85`) then windows reconstructed sessions, not raw files — no change needed at the call sites once `collect()` returns reconstructed sessions.

### C. `telemetry/report.py` — `<synthetic>` filter + tier normalization + corrected cost KPI

`SessionStats` (`report.py:52-155`) already reads per-message `msg.get("model")` into `self.models` (`report.py:96-98`) and splits main/sub on `isSidechain` (`report.py:99`). Add:

```python
TIER = {"claude-opus-4-8": "opus", "claude-sonnet-4-6": "sonnet",
        "claude-haiku-4-5-20251001": "haiku"}
def tier_of(model: str) -> str | None:
    if model == "<synthetic>": return None          # filtered everywhere
    for raw, t in TIER.items():
        if raw in model: return t
    return "opus" if "opus" in model else ...        # substring fallback, matches rates_for()
```

In `add_assistant()` (`report.py:73-125`), skip usage accounting when `tier_of(model) is None` (drop `<synthetic>`), and accumulate a new per-tier, **main-thread-only** input bucket:

```python
# only when not rec.get("isSidechain") and tier is not None:
self.main_input_by_tier[tier] += inp + cr + cw     # total input on the main thread
```

Add the headline derived KPI on `SessionStats`:

```python
def main_thread_opus_input_share(self) -> float:
    total = sum(self.main_input_by_tier.values())
    return self.main_input_by_tier["opus"] / total if total else 0.0
```

This is the corrected unit from [ADR-0001](../adr/0001-real-usage-measurement-baseline.md): sidechain-excluded, `<synthetic>`-filtered, tier-normalized, main-thread only.

### D. `telemetry/report.py:to_json()` (`report.py:259-277`) and `print_human()` — emit corrected unit, relabel `$est`

Add to the `to_json()` dict (`report.py:263-276`):

```python
"models": {tier_of(m) or "synthetic": c for m, c in st.models.items()},  # tier labels, not raw ids
"synthetic_excluded": count of <synthetic> records,
"main_thread_opus_input_share": round(st.main_thread_opus_input_share(), 4),
"est_cost_usd": round(st.cost, 4),          # unchanged value
"est_cost_label": "API-equivalent proxy (not the owner's bill)",
```

In `print_human()` totals (`report.py:240-250`), add a primary cost line and demote dollars:

```
  opus main-thread share : {share:.1%}   (PRIMARY cost KPI — Opus consumption / rate-limit headroom)
  est. cost (API-equiv)  : ${agg_cost:.2f}   (secondary proxy, NOT the owner's bill — verify PRICING)
```

The dollar number stays; only its framing changes, per the cost-framing correction in the ADR.

### E. `--baseline <dir>` diff on `report.py` and `gate.py`

Add `--baseline DIR` to both argparsers. When set, parse the frozen corpus the same way (`collect(Path(args.baseline), project)`), compute the same metrics over it, and print a per-metric delta table (live vs frozen): fresh-input/session, weighted cache hit%, `main_thread_opus_input_share`, subagent share, `$est` (labeled). `gate.py:evaluate()` (`gate.py:44-64`) gains an optional `baseline_sessions` arg and returns the frozen weighted hit rate alongside the live one so the gate can report "live 0.96 vs frozen 0.95 — no regression," not just an absolute floor.

### F. `telemetry/INTEGRATION.md` — wire telemetry into the program

Add a section "Wave 0 — baseline before install" documenting: run `snapshot.py` and a 2–3 day before-window *before* the P0 install; the headline cost unit is `main_thread_opus_input_share`, not dollars; `$est` is a labeled secondary proxy; the gate uses `--baseline` for relative (not just absolute-floor) regression checks. This closes the "telemetry is orphaned from plans/00" gap the ADR names.

## Why each change (one cited finding + impact each)

- **A (snapshot.py):** *Finding* — a before/after with no captured before is not an experiment; CursorBench compares against a frozen reference corpus precisely to make a change attributable ([Agent Wars / CursorBench](https://agent-wars.com/news/2026-03-13-how-cursor-compares-model-quality-with-cursorbench)). *Impact* — closes the critical "no before" gap so post-install fresh-input tokens/session down ≥15% and cache% deltas are attributable to config, not task drift.
- **B (session reconstruction):** *Finding* — subagent transcripts are separate files under `.../subagents/...` and `report.collect()` globs `**/*.jsonl` taking the N most-recent *files* (`report.py:179-189`), so one task fans out into many "sessions" (critique P0-2, verified: the most-recent file in the sample IS a subagent file). *Impact* — every per-session metric (turns, latency, cost-per-task in [impl 02](02-quality-latency-proxies.md)) is otherwise corrupted; reconstruction is the prerequisite for all of them.
- **C/D (filter + corrected unit):** *Finding* — the real corpus is Opus 5421 / Haiku 1335 / Sonnet 219 / `<synthetic>` 53 with 28% sidechain, so a blended "Opus share >80%" baseline is empirically wrong and a per-message model + `isSidechain` are directly computable from the JSONL ([Claude Code sub-agents docs](https://code.claude.com/docs/en/sub-agents)). *Impact* — the routing KPI in [impl 05](05-model-tiering-routing.md) becomes interpretable (main-thread, real-model, the population a routing rule can move) instead of moving for background-spawn noise.
- **D (relabel `$est`):** *Finding* — `report.py` itself warns its dollar figures are "estimates … not invoices" (`report.py:18-20`) and the owner is on a flat Max subscription governed by usage caps, not per-token billing. *Impact* — the headline cost KPI matches the real constraint (Opus consumption / rate-limit headroom); no number implies a charge the owner does not pay.
- **E (`--baseline` diff):** *Finding* — variance-reduced before/after needs the pre-period as the reference ([Optimizely CUPED](https://www.optimizely.com/optimization-glossary/what-is-cuped)). *Impact* — turns the frozen corpus into a one-command per-metric delta the scorecard ([impl 04](04-gain-scorecard-experiment.md)) reads.

## Build order (step by step)

1. Add the `telemetry/baseline/` ignore rule to `.gitignore` (the corpus is machine-local and must never be committed).
2. Write `telemetry/snapshot.py` (change A). Run it once to freeze the pre-install corpus and confirm the manifest carries date + repo SHA.
3. Add `tier_of()` / `TIER` and the `<synthetic>` filter + `main_input_by_tier` to `SessionStats` (change C). Unit-check `tier_of` on the three real ids and `<synthetic>`.
4. Reconstruct sessions in `collect()` (change B); confirm a fanned-out workflow collapses to one reconstructed session.
5. Emit the corrected unit and relabel `$est` in `to_json()` / `print_human()` (change D).
6. Add `--baseline` to `report.py` and `gate.py` (change E); thread the optional frozen-window arg through `gate.evaluate()`.
7. Document Wave 0 in `INTEGRATION.md` (change F).

## Validation commands and targets

```bash
# 1. Freeze the pre-install corpus (run BEFORE the P0 install)
python3 telemetry/snapshot.py --note "pre-P0 baseline"
#   -> telemetry/baseline/2026-06-26-<sha>/ with manifest.json (date + repo SHA); rerun must refuse to overwrite.

# 2. Session reconstruction: a fanned-out workflow is ONE reconstructed session
python3 telemetry/report.py --last 30 --json | python3 -c "import json,sys; s=json.load(sys.stdin); print('sessions:', len(s))"
#   Target: reconstructed session count <= raw .jsonl count for any window with a fan-out;
#           the fan-out session shows non-zero subagent token share.

# 3. Corrected headline unit, filters applied
python3 telemetry/report.py --last 30 --json | python3 -c "import json,sys; s=json.load(sys.stdin)[0]; print(s['main_thread_opus_input_share'], s['models'])"
#   Target: share in [0,1] and LOWER than the naive blended share; model keys are {opus,sonnet,haiku}, never raw ids or <synthetic>.

# 4. Baseline diff
python3 telemetry/report.py --baseline telemetry/baseline/<tag> --last 30
#   Target: per-metric delta table (live vs frozen). Post-install: fresh-input/session down >=15%, cache% not below frozen.

# 5. Gate, relative to frozen window, still zero-token and honest about units
python3 telemetry/gate.py --baseline telemetry/baseline/<tag> --last 20 --json
#   Target: reports live vs frozen weighted hit rate; exit 0 when not regressed.
```

## Dependencies and sequencing

- **Wave placement: Wave 0.** This is the first thing that lands and the hard gate on the program: it MUST precede the P0 install ([`plans/00-master-plan.md`](../00-master-plan.md) BUG-01..23, PORT-01..12), because once the new config is installed the pre-config window is gone and every before/after number is unattributable.
- **depends_on:** nothing — it is read-only, stdlib, and P0-independent by construction.
- **Depended on by:** [impl 02](02-quality-latency-proxies.md) (proxies parse the reconstructed corpus), [impl 03](03-eval-backbone-canary.md) (tier-label normalization feeds the differential harness's `results/<tier>/` keying), [impl 04](04-gain-scorecard-experiment.md) (scorecard reads `--baseline` deltas and the corrected unit), [impl 05](05-model-tiering-routing.md) (routing KPI = `main_thread_opus_input_share`).

## Risks and mitigations

- **R1 — routing-share confounded by the existing mix (critique P0-1).** *Mitigation:* the KPI excludes `isSidechain` and `model == "<synthetic>"` and is main-thread/interactive only (change C); the frozen corpus captures the real present share so the [impl 05](05-model-tiering-routing.md) target is calibrated, not assumed.
- **R2 — wrong session unit (critique P0-2).** *Mitigation:* `collect()` reconstructs logical sessions before windowing (change B); validated by the "fan-out collapses to one session" check.
- **R3 — `<synthetic>` corrupts per-model math (critique minor note).** *Mitigation:* `tier_of()` returns `None` for `<synthetic>`, which is skipped in all model-segmented accounting and surfaced only as a `synthetic_excluded` count.
- **R4 — assumed-zero adoption baseline inflates "improvement" (critique minor note).** *Mitigation:* `snapshot.py` freezes the *real* pre-install rate; downstream ADRs diff against the captured number, never zero.
- **R5 — dollars misread as a bill.** *Mitigation:* `$est` is relabeled "API-equivalent proxy (not the owner's bill)" and demoted below the main-thread Opus-share line (change D).
- **R6 — `snapshot.py` accidentally overwrites a frozen corpus.** *Mitigation:* the tag directory is append-only; an existing tag makes `snapshot.py` exit without writing.

## Effort and checklist

Effort: **M** (one new ~80-line read-only script, plus surgical edits to `collect()`, `SessionStats`, `to_json`/`print_human`, and two argparsers — all stdlib, no new dependencies).

- [ ] `.gitignore` ignores `telemetry/baseline/`.
- [ ] `telemetry/snapshot.py` freezes a date+SHA-tagged, append-only corpus with a manifest.
- [ ] `collect()` reconstructs logical sessions (subagent files grouped under parent).
- [ ] `tier_of()` + `<synthetic>` filter + `main_input_by_tier` on `SessionStats`.
- [ ] `main_thread_opus_input_share` emitted in `to_json()`; tier-label model keys; `synthetic_excluded` count.
- [ ] `$est` relabeled "API-equivalent proxy (not the owner's bill)" and demoted below the Opus-share line in `print_human()`.
- [ ] `--baseline DIR` diff on `report.py` and `gate.py`; `gate.evaluate()` reports live vs frozen.
- [ ] `INTEGRATION.md` documents Wave 0 (baseline before install; corrected unit; relative gate).
- [ ] All five validation commands pass against the owner's real `~/.claude/projects`.
