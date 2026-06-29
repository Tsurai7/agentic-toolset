# docs

Long-form documentation that doesn't belong in a skill, principle, or the always-on prefix.
Unlike `core/`, nothing here is rendered into provider configs — these are for humans (and
agents that go looking).

| Path | What |
|------|------|
| [`design/model-orchestration-office-hours.md`](design/model-orchestration-office-hours.md) | The gstack `office-hours` forcing-questions session that scoped the model-orchestration work (why it's a skill, not an always-on principle). |
| [`research/ai-native-agentic-engineering.md`](research/ai-native-agentic-engineering.md) | Reviewed, cited snapshot of how Anthropic / OpenAI / Google / Cursor do model orchestration + token efficiency, and the vendor-neutral patterns. |
| [`guides/ai-for-software-engineering.md`](guides/ai-for-software-engineering.md) | Practitioner playbook: spec → context → plan → small diff → verify → review, with model tiering and the known failure modes. |
| [`guides/ai-in-daily-life.md`](guides/ai-in-daily-life.md) | Practical everyday-use guide: pick the right tool/tier, research, writing, learning, decisions, plus literacy & safety habits. |

These feed the [`model-orchestration`](../core/skills/model-orchestration/SKILL.md) skill and
the [`catalog/plugins.yaml`](../catalog/plugins.yaml) `ponytail` entry.
