# 评测

[English](evaluation.md) · [全部指南](README.md)

`bench eval` 执行 Agent 与 benchmark 的 case，`bench status` 查询状态，
`bench compare` 检查两份结果是否可比较。Benchmark 提供任务定义和原生得分；
Agent 配置控制策略、上下文和模型预算。

## 选择 case 与执行方式

本地 Docker benchmark 使用 `--registry-root /path/to/registry`；已有 HTTP 服务使用
`--benchmark-url NAME=https://benchmark.example`。重复 `--benchmark` 选择多个
benchmark，重复 `--task NAME:TASK_ID` 选择任务，重复 `--seed` 选择种子。
有效任务 ID 和种子来自 manifest 或远程 catalog，不同系列的任务 ID 不一定相同。

支持的名称是 `libero`、`libero_pro`、`libero_long_plus_plus`、`libero_ultra_long`。
PRO 和 LiLo manifest 提供 `official` 与明确命名的 `migration_subset` 两种 profile。
改变 profile 或物理步数预算会改变评测条件。

Agent 来源五选一：`--agent-config`、`--agent-matrix`、`--agent-factory`、
`--agent-url`、`--agent-artifact-store`。工厂和外部服务需要显式 `--agent-version`；
preset 根据展开后的输入计算版本。对 preset 或 Agent matrix 添加 `--dry-run`，
可验证并输出计划而不启动 case 服务。

本地 Docker 评测可用 `--max-concurrent N` 设置并发数。远程 HTTP 评测按顺序执行。
`--timeout-s` 限制单次通信，`--case-timeout-s` 限制整个 case。每次运行使用新的
`--run-id`。

## 查看输出

```bash
bench status --results-root /absolute/path/to/results --run-id model-1
```

JSON 响应包含 case 状态及错误。Case 输出包括 `result.json`、原生得分文件、
下载后的 `media/` 和 `runner_trace/`，模型 Agent 还会保存配置指定的 trace。
`provenance` 保存请求的身份，`runtime.observed` 保存验证得到的运行信息。
仅声明一个 Agent 版本名并不代表已经验证其依赖环境。

如果希望结果目录写入失败后仍能查询状态，可用 `--status-root` 指定独立目录。
查询时也应传入相同的 status-root。

要查看已记录的模型轨迹，传入包含 `trace/events.jsonl` 的 Agent 输出目录，
并指定一个新建或空的报告目录：

```bash
roborsi-trajectory /absolute/path/to/agent-output \
  --output /absolute/path/to/trajectory-report
```

在本地打开生成的 `index.html`。报告展示已记录的轮次，并将其引用的媒体复制到报告目录。

## 恢复批次

重复原评测命令，换一个新 run ID，并添加 `--resume-from PREVIOUS_RUN_ID`。
保持 benchmark 条件、Agent 输入和所选 case 一致。Runner 复用兼容的已完成结果，
重试允许重试的失败或尚未发布结果的 case。前一 worker 仍持有执行锁时会拒绝恢复。
恢复记录保留到旧结果的引用，不覆盖旧运行。

## 比较结果

从 `bench status` 获取 case ID：

```bash
bench compare --results-root /absolute/path/to/results \
  --left-run model-1 --left-case LEFT_CASE_ID \
  --right-run model-2 --right-case RIGHT_CASE_ID
```

默认策略要求评测条件一致，并具有已验证的运行信息。缺失证据会报告不可比较。
例如，远程 HTTP 元信息不能证明本地检查过 Docker 镜像摘要。解释得分差异前，
应先查看报告中的不一致项。

可用 `--comparison-policy` 提供 JSON `ComparisonPolicy`，显式策略会记录在比较结果中。
保存 Agent 源码与依赖环境用于可复现评测，本身不依赖自动改进流程。

## 验证范围

离线测试用确定性的环境替身验证 schema、本地 HTTP、清理、批次恢复及文件持久化。
可选的 [LIBERO 原生测试](../tests/README.md#libero-cpu-evaluation-check) 还会执行真实
模拟器，并与直接调用原生环境的得分比较。固定动作集成测试不代表模型任务成功率。
