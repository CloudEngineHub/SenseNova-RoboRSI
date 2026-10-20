# Benchmark release guides

This release contains the Agent runtime, benchmark evaluation, and adapters for
LIBERO, LIBERO-PRO, LIBERO Long++, LIBERO Ultra-Long, Bench2Dex and BEHAVIOR-1K.
Benchmark task definitions and scoring belong to each native runtime.

| Guide | English | 简体中文 |
| --- | --- | --- |
| Installation and first evaluation | [Getting started](getting-started.md) | [快速开始](getting-started.zh-CN.md) |
| Model, prompt, context and budgets | [Agents](agents.md) | [Agent 配置](agents.zh-CN.md) |
| Batch execution, results and comparison | [Evaluation](evaluation.md) | [评测](evaluation.zh-CN.md) |

The benchmark build recipes are in [LIBERO](../benchmarks/libero/README.md),
[LIBERO-PRO](../benchmarks/libero_pro/README.md),
[Long++ / Ultra-Long](../benchmarks/libero_lilo/README.md),
Bench2Dex ([English](../benchmarks/bench2dex/README.md) /
[简体中文](../benchmarks/bench2dex/README.zh-CN.md)), and
BEHAVIOR-1K ([English](../benchmarks/behavior_1k/README.md) /
[简体中文](../benchmarks/behavior_1k/README.zh-CN.md)).
See [the test guide](../tests/README.md) for offline and native checks.

Generic EmbodiedAgent presets can connect to the supported services.
