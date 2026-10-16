# Evaluation

[简体中文](evaluation.zh-CN.md) · [All guides](README.md)

`bench eval` runs Agent–benchmark cases, `bench status` queries their state, and
`bench compare` checks whether two saved results are comparable. The benchmark
supplies task definitions and native scores. Agent configuration controls the
policy, context and model budgets.

## Select cases and execution

Use either `--registry-root /path/to/registry` for local Docker benchmarks or
`--benchmark-url NAME=https://benchmark.example` for an existing HTTP service.
Repeat `--benchmark` to select benchmark names, `--task NAME:TASK_ID` to select
tasks, and `--seed` to select seeds. Available task IDs and seeds come from the
manifest or remote catalog; do not assume that task IDs match across families.

Supported names are `libero`, `libero_pro`, `libero_long_plus_plus`, and
`libero_ultra_long`. PRO and LiLo manifests expose an `official` profile and an
explicit `migration_subset` profile. Changing the profile or physical step
budget changes the evaluation condition.

Select exactly one Agent source: `--agent-config`, `--agent-matrix`,
`--agent-factory`, `--agent-url`, or `--agent-artifact-store`. Factories and
external Agent services need an explicit `--agent-version`; a preset derives
its version from its resolved inputs. `--dry-run` validates and prints a preset
or Agent matrix plan without starting case services.

Local Docker evaluation accepts `--max-concurrent N`. Remote HTTP evaluation
runs sequentially. Set `--timeout-s` for individual transport calls and
`--case-timeout-s` for a complete case. Provide a new `--run-id` for each run.

## Inspect saved outputs

```bash
bench status --results-root /absolute/path/to/results --run-id model-1
```

The JSON response reports case state and errors. Case output includes
`result.json`, native score artifacts, downloaded `media/`, and `runner_trace/`.
Model Agents also write their configured trace. Requested identities are in
`provenance`; verified runtime evidence is in `runtime.observed`. A declared
Agent label alone does not establish a verified dependency environment.

Use `--status-root` to save state in a separate directory when result-storage
failures need to remain queryable. Keep the same status-root option when querying.

To inspect a recorded model trajectory, pass the Agent output directory that
contains `trace/events.jsonl` and a new or empty report directory:

```bash
roborsi-trajectory /absolute/path/to/agent-output \
  --output /absolute/path/to/trajectory-report
```

Open the generated `index.html` locally. The report includes the recorded turns
and copies their referenced media into the report directory.

## Resume a batch

Repeat the original evaluation command with a fresh run ID and
`--resume-from PREVIOUS_RUN_ID`. Keep benchmark conditions, Agent inputs and
selected cases the same. The runner reuses compatible completed results and
retries eligible failures or unpublished cases. It rejects resume while the
previous worker owns the execution lock. Resume records preserve links to the
earlier results; they do not overwrite the earlier run.

## Compare results

Use case IDs from `bench status`:

```bash
bench compare --results-root /absolute/path/to/results \
  --left-run model-1 --left-case LEFT_CASE_ID \
  --right-run model-2 --right-case RIGHT_CASE_ID
```

The default policy requires matching evaluation conditions and verified runtime
information. Missing evidence produces a non-comparable report. In particular,
remote HTTP metadata cannot establish a locally inspected Docker digest.
Inspect the reported mismatches before interpreting score differences.

The optional `--comparison-policy` accepts a JSON `ComparisonPolicy`; this
explicit policy is part of the comparison record. Saved Agent sources and
dependency environments remain useful for reproducible evaluation, independently
of any improvement workflow.

## Validation limits

Offline tests exercise schema validation, local HTTP, cleanup, batch resume and
artifact persistence with deterministic native facades. The opt-in
[LIBERO native tests](../tests/README.md#libero-cpu-evaluation-check) also execute
the real simulator and compare its score with direct native calls. A
fixed-action integration check is not a model success-rate measurement.
