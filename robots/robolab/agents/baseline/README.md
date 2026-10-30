# Standard RoboLab Agent

This preset uses the default `EmbodiedAgent` factory with
`agent.planner: codex_cli`. The framework owns `CodexCliPlanner`, `codex exec`,
the per-case workspace and the native-action MCP server. The Agent does not start
the historical app-server or implement a second decision loop.

The delivered configuration selects `gpt-6-astra`, effort `max`, Codex CLI
`0.160.0`, and the Responses endpoint `https://api.openai.com/v1`. API-key
authentication uses `OPENAI_API_KEY`. The second authorized smoke test used that
same address with an explicit proxy environment and received a model response,
but CLI approval policy `never` prevented the simulation
MCP action from executing. There is no canonical episode score from that run.
The framework now accepts `mcp_servers.roborsi.tools.roborsi_action.approval_mode`
with value `approve` in MCP mode, and this preset enables it while retaining
global policy `never`. Standard model acceptance still requires a new real-model
run with this configuration.
The historical 57.083333% result is not this Agent's score. Only this CLI backend
is declared by the preset.

`prompt.md` describes base-link Cartesian position, wxyz quaternion, binary
gripper and physical control frames. Tools are supplied by the Task action
schema through the framework. No extra Skill, custom Context implementation,
VLA, model SDK plugin or benchmark-specific Agent Python factory is needed.

## Install outside the checkout

Use the `$REPO` and `$WORK` variables from the
[benchmark README](../../../../benchmarks/robolab/README.md). Build the core wheel
there first. Exporting the Agent includes the inherited preset and prompt in an
independent package; the resulting bundle does not depend on a source checkout.

```bash
cd "$REPO"
"$WORK/dev/bin/python" -m roborsi.agents.package \
  --config "$REPO/robots/robolab/agent.yaml" --name "robolab_baseline" \
  --output "$WORK/agent-project"
"$WORK/dev/bin/python" -m build --wheel \
  --outdir "$WORK/agent-dist" "$WORK/agent-project"

uv venv --python "3.11" "$WORK/agent"
uv pip install --python "$WORK/agent/bin/python" \
  "$WORK"/core-dist/roborsi-*.whl \
  "$WORK"/agent-dist/roborsi_agent_bundle_robolab_baseline-*.whl \
  -r "$REPO/robots/robolab/agents/baseline/requirements.lock.txt"
uv pip check --python "$WORK/agent/bin/python"

"$WORK/runner/bin/python" -m robots.robolab.agents.historical.install_codex \
  --destination "$WORK/codex"
```

The CLI installer downloads both historical versions into a private directory,
verifies archive/native binary hashes and retains their companion executables.
Use the `0.160.0` entry from `$WORK/codex/binaries.json` for this standard preset;
it must be on this process's `PATH`. The expected native executable SHA-256 is
`12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad`.
No global npm installation is necessary.

```bash
CODEX_BIN_DIR="$("$WORK/runner/bin/python" -c \
  'import json,pathlib,sys; print(pathlib.Path(json.load(open(sys.argv[1]))["0.160.0"]).parent)' \
  "$WORK/codex/binaries.json")"
cd "$WORK"
PATH="$CODEX_BIN_DIR:$PATH" "$WORK/agent/bin/roborsi-check-llm" \
  --agent-config "bundle:robolab_baseline" --preflight-only --json
```

The preflight requires the configured environment key to exist but does not send
a model request. An explicitly labelled dummy key can be used only for this
offline check; a successful preflight does not prove model access. Real calls
require locally provisioned credentials. Keep the selected CLI directory on
`PATH` when running `bench eval`; the preset forwards `PATH` and `OPENAI_API_KEY`
to its isolated CLI environment.

For a different compatible Responses endpoint, pass an explicit quoted override:

```bash
--agent-set '/agent/codex_cli/config_overrides/model_providers.robot_harness.base_url="https://your-provider.example/v1"'
```

The JSON-pointer path preserves the dots inside the TOML override key. Check
the accepted configuration with preflight before a paid run. The provider
override is part of the experiment identity. `OPENAI_BASE_URL` alone does not
override this standard preset. Do not record the credential value in a preset,
wheel, result or shell command shared with others.

If the provider requires a network proxy, explicitly forward the proxy variable
names that are configured in the Agent's environment. The isolated CLI does not
inherit them by default, and each name in `env_vars` must exist. Generate the
override without printing or storing proxy values:

```bash
ROBOLAB_CLI_ENV_NAMES="$("$WORK/agent/bin/python" - <<'PY'
import json
import os

names = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
         "http_proxy", "https_proxy", "all_proxy", "no_proxy"]
print(json.dumps(["PATH", "OPENAI_API_KEY", *[name for name in names if name in os.environ]]))
PY
)"
```

Add `--agent-set "/agent/codex_cli/env_vars=$ROBOLAB_CLI_ENV_NAMES"` to the
preflight and evaluation commands. Keep `inherit_env: false`. The framework
adds `127.0.0.1,localhost` to the CLI's `NO_PROXY` and `no_proxy` for its local
MCP service. Record the selected variable names as part of the experiment;
an offline CLI preflight alone does not establish provider connectivity.

## Budgets and evidence

`max_turns` and `max_tokens` must remain `null` for this backend. The default
planner timeout is disabled (`0`), while each action has a 1200-second timeout.
The one-case example sets planner and Runner timeouts explicitly. An action's
`steps` counts native control frames, and the adapter stops at the unchanged
Task budget or native success. Timeout, model exit and a terminal tool response
are not success; the Benchmark owns the final outcome and score.

Record the core wheel/hash, Agent wheel/hash, installed environment lock,
preflight JSON, actual provider/model and Runner output. A real-model acceptance
must additionally verify that the fixed CLI's MCP return contains the current
terminal token and that its processes are cleaned up. Use the canonical Benchmark
result to determine the episode outcome.
