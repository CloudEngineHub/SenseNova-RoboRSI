# Historical full-task 1x policy

This is the compatibility entry for the original `codex app-server` / goals /
dynamic-tools experiment. It preserves the recorded DROID/no-exploration policy,
prompts, image conversion, trajectory interpolation and protocol-2 feedback
barrier. It is separate from the standard `EmbodiedAgent` / `codex exec` preset.
Its 57.083333% reference score must not be attributed to the standard Agent.

The simulator and this policy run in separate processes and Python environments.
The native client sends only DROID proprioception and the exterior/wrist images.
Images are resized with Pillow LANCZOS to fit 320 × 320 while retaining aspect
ratio. Actions are float32 base-link XYZ, wxyz quaternion and binary gripper;
linear translation plus SciPy SLERP is used when expanding trajectories.

## Install and run

Use the external `$WORK` and source `$REPO` from the
[benchmark README](../../../../benchmarks/robolab/README.md):

```bash
uv venv --python "3.11" "$WORK/historical-agent"
uv pip install --python "$WORK/historical-agent/bin/python" \
  -r "$REPO/robots/robolab/agents/historical/requirements.lock.txt"
uv pip check --python "$WORK/historical-agent/bin/python"

cd "$REPO"
"$WORK/runner/bin/python" -m robots.robolab.agents.historical.install_codex \
  --destination "$WORK/codex"
```

If the same private CLI installation was already prepared for the standard
Agent, reuse its `binaries.json`; the installer deliberately refuses an existing
destination. `codex-binaries.json` locks official Linux x86_64 package archives,
versions, native executables and companion package members.

The Python lock contains exactly NumPy 2.3.1, SciPy 1.17.0, Pillow 12.1.1,
msgpack 1.2.1 and websockets 16.1.1. This host is not the native Python 3.12
environment and needs no Isaac, OpenPI or model SDK installation. The source
checkout supplies the compatibility modules; the full-task launcher sets its
working directory explicitly and invokes the separately supplied `--agent-python`.

Provision `OPENAI_API_KEY` in the Agent process environment. This historical
client reads `OPENAI_BASE_URL`, falling back to `https://api.openai.com/v1`.
The plan and effective Agent configuration record the provider name, wire API
and SHA-256 of that exact endpoint. Recovery rejects changed endpoints and legacy
plans without an endpoint identity. Native containers receive neither variable.
The original logged model was `gpt-6-astra`, effort `max`, with a 1200-second
request timeout and 30 configured transport retries. No exploratory tools or
G2 route are enabled.

Use `python -m benchmarks.robolab.reproduce` from the Runner environment, as shown
in the main README. It prints the plan by default; `--execute` starts paid model
calls. It checks both native executable hashes, records effective policy and
prompt settings, and runs the exact completed reset cohorts. The older CLI
handled 1168 recorded trials; CLI 0.160.0 handled the remaining 32.

Each policy has one active native connection. Native disconnect/cancellation
aborts its episode and shuts down the owned app-server group. Each task's
original native client is closed before replacement. The launcher always cleans
up the native container and host server, including failure paths; partial logs
remain available for diagnosis. `--resume` accepts complete original process
boundaries only, as explained in the main README.

## What this preserves

The system and note prompts match the source anchor's bytes. The original
executor and image helpers are retained for this route; unused API, G2, pi0.5,
retry-5x and exploration routes are omitted. The server implements the existing
NumPy msgpack wire contract locally so the policy does not need the unrelated
OpenPI installation. The native image's WebSocket client has compatibility
changes only; native task definitions and scoring remain pinned and verified.

The known source commits are provenance anchors, not proof of the exact dirty
working tree used for every historical run. Interrupted unscored attempts are
excluded. See [PROVENANCE.md](../../../../benchmarks/robolab/PROVENANCE.md) for
reset cohorts, source hashes, CLI distribution and the environment limits.
