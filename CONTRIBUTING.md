# Contributing

[简体中文](CONTRIBUTING_zh.md)

This release covers the Agent runtime and benchmark evaluation for the LIBERO
family and Bench2Dex. Keep
contributions focused on this scope and preserve supported interfaces.

1. Verify the actual Git remote, branch and upstream before editing. Read the
   implementation and callers on both sides of a changed interface.
2. Start from what users need to observe and control. Keep framework mechanisms
   separate from replaceable Agent policies; reuse configuration, RPC, runtime
   and artifact helpers.
3. Keep native behavior under `robots/<benchmark>/`, including `libero`
   and `bench2dex`. Import simulator and model dependencies where used
   so package imports and CLI help stay available without native stacks.
4. Follow neighboring types, Google-style docstrings and project logging.
   Validate external input at its owning boundary and make cleanup explicit.
5. Test observable behavior with existing fixtures. Update the corresponding
   English and Chinese guides under `docs/` when behavior changes.

## Development environment and checks

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[runtime,test]'
python -m pip install pre-commit==4.6.2
pre-commit install
pre-commit run --all-files
pytest tests/unit_tests -q
```

See [tests/README.md](tests/README.md) for native opt-in checks. Required CI runs
offline unit tests on Linux, with Python 3.11 and 3.12. No model service,
simulator, asset download or GPU is required for those tests.

## Pull requests

Create development PRs against `main` in the actual target repository. Before
opening a PR, fetch that remote and rebase the feature branch onto its latest
`main`, then rerun the relevant checks. Group related changes by feature; one
PR may contain multiple commits. Use Conventional Commits such as
`fix(evaluation): preserve native score after cleanup`.

Describe the user-visible change, compatibility or migration requirements, and
checks actually run. Distinguish offline integration from native simulator or
model success. Review the complete diff before publishing.

Never weaken failing tests to make a change pass. Do not commit credentials,
local deployment settings, logs, model checkpoints, downloaded assets or
generated results. Keep existing license and attribution notices.
