# LIBERO release guides

This release contains the Agent runtime, benchmark evaluation, and the LIBERO,
LIBERO-PRO, LIBERO Long++, and LIBERO Ultra-Long adapters. Benchmark task
definitions and scoring belong to each native runtime.

| Guide | English | 简体中文 |
| --- | --- | --- |
| Installation and first evaluation | [Getting started](getting-started.md) | [快速开始](getting-started.zh-CN.md) |
| Model, prompt, context and budgets | [Agents](agents.md) | [Agent 配置](agents.zh-CN.md) |
| Batch execution, results and comparison | [Evaluation](evaluation.md) | [评测](evaluation.zh-CN.md) |

The benchmark build recipes are in [LIBERO](../benchmarks/libero/README.md),
[LIBERO-PRO](../benchmarks/libero_pro/README.md), and
[Long++ / Ultra-Long](../benchmarks/libero_lilo/README.md).
See [the test guide](../tests/README.md) for offline and native checks.

Recursive improvement, training, other robot stacks, and historical private
experiment configurations are outside this release. Model checkpoints, scene
datasets and historical ICL packages are not included.
