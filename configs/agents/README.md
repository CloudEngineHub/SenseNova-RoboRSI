# Agent presets

`embodied/` contains general Agent configurations for all supported LIBERO
benchmarks. Choose the model, prompt, context and budgets in a preset; choose
benchmark tasks and seeds through `bench eval`.

| Preset | Purpose |
| --- | --- |
| `embodied/default.yaml` | Model API, eight recent feedback turns |
| `embodied/short_context.yaml` | Same model, four recent feedback turns |
| `embodied/codex.yaml` | Codex SDK |
| `embodied/codex_cli.yaml` | Separately installed, pinned Codex CLI |
| `embodied/claude_code.yaml` | Claude SDK |

All model names are placeholders. Credentials come from the Agent environment;
do not put them in YAML. `source_root` is relative to the preset file.
[`../evaluations/embodied.yaml`](../evaluations/embodied.yaml) compares the two
API context choices through `--agent-matrix`.

See [Agents](../../docs/agents.md) / [Agent 配置](../../docs/agents.zh-CN.md)
for overrides and portable package export, and
[Evaluation](../../docs/evaluation.md) / [评测](../../docs/evaluation.zh-CN.md)
for execution and results.
