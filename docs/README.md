# docs

Long-form documentation that doesn't belong in a skill, principle, or the always-on prefix.
Unlike `core/`, nothing here is rendered into provider configs — these are for humans (and
agents that go looking).

| Path | What |
|------|------|
| [`design/model-orchestration-office-hours.md`](design/model-orchestration-office-hours.md) | The gstack `office-hours` forcing-questions session that scoped the model-orchestration work (why it's a skill, not an always-on principle). |
| [`research/ai-native-agentic-engineering.md`](research/ai-native-agentic-engineering.md) | Reviewed, cited snapshot of how Anthropic / OpenAI / Google / Cursor do model orchestration + token efficiency, and the vendor-neutral patterns. |
| [`research/token-and-performance-improvements.md`](research/token-and-performance-improvements.md) | **The improvement research.** 2026 SOTA token-reduction + performance methods mapped onto agentic-cfg's measured data; what to keep/fix/drop; each rec a testable hypothesis. |
| [`research/current-design-critique.md`](research/current-design-critique.md) | Adversarial keep/fix/drop audit of the current methods, grounded in the repo's own n=3 over-tooling data. |
| [`research/improvement-roadmap.md`](research/improvement-roadmap.md) | Prioritized roadmap (instrument-first); each item names the benchmark cell that decides it. |
| [`research/swe-benchmark-design.md`](research/swe-benchmark-design.md) | Methodology for [`evals/swe_bench.py`](../evals/swe_bench.py) — difficulty ladder × model tiers, metrics, gameproofing, small-n verdicts. |
| [`research/benchmark-results.md`](research/benchmark-results.md) | **Live measured run** (Opus/Sonnet/Haiku × 5 tiers). Reproduces the two-regime split, surfaces that Sonnet over-tools too, and shows the "3×" input is ~95% free cache (billed overhead ~1.1–1.2×). |
| [`guides/ai-for-software-engineering.md`](guides/ai-for-software-engineering.md) | Practitioner playbook: spec → context → plan → small diff → verify → review, with model tiering and the known failure modes. |
| [`guides/ai-in-daily-life.md`](guides/ai-in-daily-life.md) | Practical everyday-use guide: pick the right tool/tier, research, writing, learning, decisions, plus literacy & safety habits. |

These feed the [`model-orchestration`](../core/skills/model-orchestration/SKILL.md) skill and
the [`catalog/plugins.yaml`](../catalog/plugins.yaml) `ponytail` entry.
