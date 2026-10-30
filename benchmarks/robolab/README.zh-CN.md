# RoboLab 全量任务 1x

[完整命令与英文说明](README.md) · [构建](BUILD.md) · [历史来源](PROVENANCE.md)

本接入提供 120 个 DROID 操作任务，复用 RoboRSI 公共 Benchmark HTTP 服务。
任务保持原生指令、seed 0 初始化、15 Hz 控制频率、300–4500 帧预算、终止规则和评分。
一次动作可推进多帧，实际消耗仍按原生控制帧计数。Agent 只能获得机械臂自身状态和两路
缩放至 320 像素的 RGB 图像，不能获得模拟器物体真值。

本次交付有两个明确区分的入口：

| 入口 | 运行方式 | 结果含义 |
| --- | --- | --- |
| 标准 RoboRSI | `EmbodiedAgent` → `CodexCliPlanner` → 固定版本 `codex exec` / MCP；120 个独立 seed 0 case | 尚未测量模型成功率 |
| 历史全量 1x | 原始 app-server/goals 策略与 native runner；按历史重启边界执行 120 × 10 次 | 现有结果审计为 685 成功、515 失败，成功率 **57.083333%**，平均原生分数 **0.6804972351963321** |

历史成功率不能归到新的标准 Agent 名下。历史脚本保留实验配置和 reset 顺序，但模型输出
具有随机性，当前容器的部分依赖也与历史主机不同，因此不能承诺再次得到完全相同的数字。

## 当前交付状态

镜像 `v0.1.2-isaac60` 已于 2026-10-21 发布，并完成按 digest 拉取及镜像检查：

```text
ghcr.io/opensensenova/sensenova-roborsi-robolab@sha256:519585576bb09c5fc4a09e6255e30d74189b86b0f8c526d3fe8d99c5031da04f
```

拉取结果与本地构建一致，依赖、源码及运行时元数据检查通过。同一镜像已通过单任务
300 帧 HTTP 执行及直接原生回放，确认 HDF5 完成落盘且所属进程正常清理；
这两项无模型检查不代表 Agent 性能。GHCR Package 为私有，
需要有读取权限的账号及本机凭据。评测固定使用上述仓库 digest；本地镜像 ID 是另一种标识，不能代替它。

本分支已在公共 `roborsi/benchmarks/runtime_source.py` 中登记 RoboLab 源码。
已发布镜像使用包含相同登记内容的组合候选版本构建。
其记录的运行源码快照为原始集成中的 `4cbb6378`，不是本 public 仓库的提交。
该镜像与从公开源码重新构建的镜像之间的区别见 [BUILD.md](BUILD.md)。

两次已授权的单任务模型联调均已结束。第二次通过显式代理配置收到预设 `https://api.openai.com/v1` 的
模型响应，但 CLI 因 `approval_policy: never` 拒绝执行需要审批的模拟动作，最终为
`agent_error`，动作执行 0 次、无原生评分。不经代理的连接探针超时。公共框架现已允许在
MCP 模式下显式批准 `roborsi_action`，本预设已启用该配置，同时保留全局策略 `never`。
标准 Agent 验收仍需重新进行真实模型联调。

## 安装与运行

使用 Linux x86_64，分别安装主控、标准 Agent、历史 Agent，原生环境放在镜像内。
[英文 README](README.md) 给出了可逐条执行的外部工作目录、锁定安装、资产准备、manifest
生成、Registry 发现及 HTTP 评测命令；标准 Agent 和历史 Agent 的安装说明分别位于
[baseline/README.md](../../robots/robolab/agents/baseline/README.md) 和
[historical/README.md](../../robots/robolab/agents/historical/README.md)。

资产固定为 RoboLab `92ccc0ee1984a272d4748c92ed73144fa806a6f4` 的 Git LFS 内容：
2228 个文件，6,141,046,362 字节，目录摘要
`718c6e372bab8f9eed3f096276f23ce03e6feb401e26456ebdb92c4d1959c62e`。
准备脚本校验后复制到外部 Registry；资产和输出不进入镜像或源码仓库，保留上游许可。

当前框架 Docker executor 固定的 1 GiB `/tmp` 不足以承载测得的原生缓存。
运行时按英文示例独立启动公共 HTTP 服务，提供 8 GiB tmpfs，再用
`--benchmark-url "robolab=http://127.0.0.1:8000"` 连接。同一服务一次只运行一个 case；
每个环境使用一个空闲 RTX GPU，冷启动可达数分钟。

历史全量计划默认为只读打印，不发起模型请求。安装并发布镜像后，在仓库根目录执行：

```bash
"$WORK/runner/bin/python" -m benchmarks.robolab.reproduce \
  --image "$IMAGE" --assets "$REGISTRY/robolab/assets/robolab" \
  --codex-binaries "$WORK/codex/binaries.json" \
  --agent-python "$WORK/historical-agent/bin/python" \
  --output "$WORK/full-task-1x" --gpus "0,1,2,3"
```

明确开始付费评测时再加 `--execute`。`--shards 0 1` 选择完整分片，默认全部八片。
脚本按五个阶段调度原来的 24 个已完成进程，不把 run 0–9 改成 seed 0–9。
`--resume` 只接续完整进程边界；遇到部分完成的进程会拒绝恢复，以免悄悄改变随机数状态。

计划与各 Agent 的 `effective-config.json` 会记录 provider 名称、wire API 和实际端点的
SHA-256。`--resume` 在启动进程前拒绝端点变化或缺少标识的旧版计划；所有 worker 使用
同一固定端点。这些配置记录不保存端点明文或密钥。

恢复时仍检查原生日志身份及可读 HDF5 中的最终分数，全量结束必须具有 1200 个唯一任务/run。
标准 CLI Agent 的 `max_turns` 和 `max_tokens` 必须为 `null`；运行时限与原生帧预算
分别设置，不应将它们描述为模型轮次或费用上限。
