# LIBERO-PRO、Long++ 与 Ultra-Long 接入说明

本文说明三套 benchmark 的冻结评测约束、镜像交付、AFS 目录布局和源码运行方式。
英文版见 [README.md](README.md)。
干净机器上的镜像拉取、registry 生成和真实模型运行命令见
[三套 LIBERO 评测复现文档](README.zh-CN.md)。

## 评测契约

| Benchmark | 全量集合 | 本次迁移子集 | 官方 1× 预算 | 主指标 |
| --- | ---: | ---: | ---: | --- |
| LIBERO-PRO Task/Swap | 8 suites × 10 tasks × 10 states = 800 | 固定 state 3 的 80 个任务 | 10,000 物理步 | 最终目标成功 |
| LIBERO-Long++ | 12 配置 × 10 次裸 reset = 120 | 固定 state 1 的 12 个配置 | 每个顺序技能 200 步 | 顺序前缀比例；全部完成才成功 |
| LIBERO-Ultra-Long | 9 配置 × 10 次裸 reset = 90 | 固定 state 1 的 9 个配置 | 每个顺序技能 200 步 | 顺序前缀比例；全部完成才成功 |

`plus9_on_failure` 默认关闭。开启后，只有在官方 1× 边界失败的案例才能在同一环境、
同一 Agent 对话内继续，累计最多 10×。正式 `result.json` 和聚合分数始终使用不可变的
1× 快照；`native/score.json` 额外记录恢复过程和真实物理步数。

Long++/Ultra-Long 的重复编号不是随机种子。官方 profile 做十次发布版裸随机 reset；
迁移 profile 明确固定为 state 1。评分器只接受发布版技能顺序的连续前缀，不用普通
LIBERO 最终目标成功替代顺序成功。

两套长序列 benchmark 使用历史冻结的
`lilo-instance-pose-feedback-v1` 观测协议。观测包含注册实例名、实时世界坐标、碰撞几何
上下界、夹爪接触、持有物体以及当前技能进度。该通道只读，不推进评分器；结果不能和
旧的纯视觉条件混为同一评测条件。

迁移接口还保留 `libero-robot-state-feedback-v1`：它将旧 v13 直接工具返回的
`robot0_eef_pos`、xyzw 四元数和 `robot0_gripper_qpos` 以具名字段随每次观测返回，同时
继续保留策略所需的 8 维 `states`。`roborsi_action` 的 action schema 对每个旧 direct-control
primitive 明确标注语义；特别是 `rotate_wrist` 表示保持末端位置的原地腕部旋转，不能用
`move_pose.target_yaw` 替代。该兼容层只恢复旧工具契约，不改变任务、评分器、初始化或
物理步数预算。

Long++ 和 Ultra-Long 子集使用 v13 的 no-tool、token-accurate 条件。PRO 使用全量 800
例参考实验的 persistent-memory ICL，并对齐 no-VLA/no-SAM3 工具面、max 推理强度、
上下文策略、轮数预算和重试策略。本仓库仍评测固定 state 3 的 80 例迁移子集，因此虽然
Agent 条件已经对齐，测试范围仍不同于全量参考。

## 交付状态与实测证据

固定 12/9/80 镜像复测使用真实模型与模拟器，遵守官方 1× 边界，没有启用
`plus9_on_failure`。与最接近历史条件的结果直接对比如下：

| Benchmark | 历史参考 | 镜像首轮 | 仅重试异常后 | 最终差值 |
| --- | ---: | ---: | ---: | ---: |
| Long++ | 12/12 | 11/12 | 11/12 | -1 |
| Ultra-Long | 8/9 | 7/9 | 8/9 | 0 |
| PRO | 78/80 | 74/80 | 79/80 | +1 |
| **合计** | **98/101** | **92/101** | **98/101** | **0** |

最终成功点数与历史参考一致，每个 benchmark 最多相差 1 点，任务能力基本接近。首轮
稳定性没有完全复现：镜像首轮 94/101 个合法原生终态，仅重试 Agent/基础设施异常后为
100/101，仍有 1 个 PRO case 无合法终态。比较边界见
[简要验证记录](README.zh-CN.md)；这里不宣称逐 case 确定性复现。

## 两种运行边界

正式可移植模式使用三个 digest 固定的镜像：PRO Benchmark、Long++/Ultra 共用的 LiLo
Benchmark，以及包含三套 Agent bundle、ICL、tokenizer 和 Python 依赖的 Agent 镜像。
目标机器不需要挂载 m 集群或 AFS；它只需要镜像、registry/manifest 配置、Docker、
模型 endpoint 和运行时注入的凭证。完整评测推荐使用 GPU 加速 MuJoCo EGL 渲染；本机
CPU 软件渲染也已验证可运行，但明显更慢。模型权重、endpoint 和凭证都不进入镜像。

以下 AFS 布局仅用于源码复现和重新准备镜像输入：

推荐布局如下：

```text
newrpent/
├── RoboRSI/                  # 纯 Git 仓库
└── work/libero_three/        # 私有配置、ICL、运行环境、日志和结果
```

`work/` 不放进仓库，原因是它含机器路径、密钥位置、大资产、生成结果和可变缓存。这样可
独立更新或替换仓库而不碰运行数据，也不会把私有路径或大文件提交到 Git。

在能挂载同一 AFS 的其他机器上，运行所需信息由两部分组成：

1. `RoboRSI/` 仓库；
2. 仓库外的一份 `source-runtime.afs.json` 私有主机配置。

主机配置必须完整指向以下依赖；无需再猜测隐含路径：

- Agent Python 或启动 wrapper；
- OpenAI-compatible endpoint 与只保存密钥的文件；
- Long++、Ultra-Long、PRO 三套密封 ICL package 根目录；
- LiLo-VLA、LIBERO、LIBERO-PRO 的固定源码树及各自 Python 环境；
- LIBERO assets、BDDL、init states，以及需要时才使用的 datasets；
- 三套上下文引擎共同使用的固定 tokenizer；
- 每套 benchmark 的固定 revision 和运行环境变量。

公开模板是 `configs/libero_three/source-runtime.example.json`，逻辑资产锁是
`benchmarks/libero_three_combined/assets.lock.json`。真实 AFS 绝对路径和密钥文件位置只写到仓库外的
私有配置。目标机器或基础容器还需要 Ubuntu 22.04 兼容的 `python3.10` 以及 Linux
EGL/GL 运行库；Python package 依赖由配置中的解释器环境或 wrapper 提供。当前 LiLo
venv 的入口明确解析到 `/usr/bin/python3.10`，所以仅挂载 AFS 但缺少该系统解释器的主机
不能直接运行 Long++/Ultra-Long。

标准 Agent 入口位于 `robots/libero/agents/three_benchmark/`。Long++ 和 Ultra-Long 通过
`v13.yaml` 继承共同的 no-tool、token-accurate 配置；PRO 使用 `pro.yaml`。
`base.yaml` 和 `v13.yaml` 只用于继承，不能直接作为评测 preset。

PRO 的 `pythonpath` 必须指向固定 revision 的 LIBERO-PRO checkout 根目录，不能指向旧的
内层 `libero/` 目录；实际导入名是 `liberopro.liberopro`。assets、BDDL 和 init states
分别由主机配置指定，可以来自独立的冻结资产包。源码评测不读取 demonstration，所以全新
checkout 没有 `liberopro/datasets/` 是正常的。发布源码中的个别 pruned init 文件可能是
空集合，部分变体 BDDL 也可能无法解析，因此用于评测的 `init_states` 和 `bddl_files` 必须
指向全量评测资产；预检会实际加载并解析 80 个选定案例，任何空集合、缺失 state 或无效
BDDL 都会在分配模拟器前失败。Ubuntu 基础环境需提供 `python3.10`、`libgl1`、
`libegl1` 和 `libglib2.0-0`。

这些系统依赖同时明确列在配置的 `system_packages` 中。预检会校验三套配置使用的
tokenizer 哈希；当前三套条件都不需要模型 checkpoint。

## 当前三套依赖策略

- 三套 preset 均为 `reasoning_effort=max`，并显式关闭 VLA 和 SAM3。
- 三套评测均走独立 Benchmark HTTP 服务和同一个 `roborsi_action` action/feedback primitive
  协议；不会启动或连接 Pi0.5/SAM3 服务。
- 三套均开启 Responses prompt caching；PRO 关闭模型重试以匹配全量参考，另外两套对
  transient transport/5xx 保留最多三次有界重试。
- 三套都使用 token-accurate 上下文策略：1,050,000 token 窗口、128,000 输出预留、
  32,768 工具/协议预留、0.75 摘要触发比例、至少保留最近 8 个完整工具往返和 2 组图像。
  `run_source.py` 从主机配置注入本地 tokenizer 及锁定
  SHA-256；在触发线以下完整保留文本历史，不能用固定 recent-turn 截断替代。

## 准备并校验 ICL

准备命令会校验源 package 的每个文件，将其复制到外部 `work/`，再校验副本并生成诊断用
`package-map.json`。权威 task-to-package map 始终保存在仓库配置中。

```bash
python benchmarks/libero_three_combined/prepare_context.py \
  --benchmark libero_long_plus_plus \
  --source /path/to/efficiency_aligned_v12 \
  --destination ../work/libero_three/longpp-icl

python benchmarks/libero_three_combined/prepare_context.py \
  --benchmark libero_ultra_long \
  --source /path/to/efficiency_aligned_v12 \
  --destination ../work/libero_three/ultra-icl

python benchmarks/libero_three_combined/prepare_context.py \
  --benchmark libero_pro \
  --source /path/to/pro_persistent_memory \
  --destination ../work/libero_three/pro-icl
```

## 一次性依赖审计

在分配模拟器前执行：

```bash
python benchmarks/libero_three_combined/check_source_runtime.py \
  --runtime-config ../work/libero_three/source-runtime.afs.json \
  --probe-python
```

该命令检查三套 Python、源码与资产目录、密钥非空、tokenizer 哈希、全部 ICL
manifest/package 哈希、12/9/80 映射数量、Agent config fingerprint 和统一的 no-tool/max
约束，并实际探测每套 Python 的关键导入、PRO 80 个选定初态和 BDDL。任一外部依赖缺失
会在启动评测前失败。

## Agent wheel 导出与仓库外安装

每个叶子 preset 都可独立导出。下面以 Long++ 为例，另外两套替换 preset 和 bundle
名称即可：

```bash
python -m roborsi.agents.package \
  --config robots/libero/agents/three_benchmark/long_plus_plus_v13.yaml \
  --name libero_long_plus_plus_v13 \
  --output /tmp/libero-longpp-agent-build
python -m build --wheel /tmp/libero-longpp-agent-build
python -m pip install /tmp/libero-longpp-agent-build/dist/*.whl
```

安装后可从仓库外使用 `--agent-config bundle:libero_long_plus_plus_v13`。ICL 本体不进入
小 wheel：源码模式仍由 `ROBORSI_LIBERO_LONGPP_ICL_ROOT` 指向外部密封包，可移植 Agent
镜像则把同一份核验副本放到 `/opt/roborsi-agent-assets/`；Ultra-Long 和 PRO 同理。wheel
声明 `roborsi[runtime]` 和 `tokenizers==0.22.2`，应与本交付对应的 RoboRSI commit
一起构建。

## 构建可移植 Agent 镜像

先把 m 集群只读来源复制到本机构建目录，再运行以下命令。准备器会拒绝多余/缺少的
package、case/package 数量错误以及与 `assets.lock.json` 不同的目录或文件 SHA-256：

```bash
python benchmarks/libero_three_combined/prepare_agent_assets.py \
  --longpp-root ../work/libero_three/longpp-icl/packages \
  --ultra-root ../work/libero_three/ultra-icl/packages \
  --pro-root ../work/libero_three/pro-icl/packages \
  --tokenizer ../work/libero_three/tokenizer/tokenizer.json \
  --output dist/agent/libero-three-assets
```

分别用 `roborsi.agents.package` 导出
`libero_long_plus_plus_v13`、`libero_ultra_long_v13` 和 `libero_pro`，导出时把
`runtime.context.tokenizer_file` 固定为
`/opt/roborsi-agent-assets/tokenizer.json`，把 `tokenizer_sha256` 固定为
`0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3`。按
`agents/python/README.md` 生成三套 wheel 和完整的 Python 3.11 hash lock，然后构建：

```bash
docker build --target libero_three -f agents/python/Dockerfile \
  --build-arg AGENT_REQUIREMENTS=dist/agent/requirements.txt \
  --build-arg 'AGENT_WHEEL=dist/agent/roborsi_agent_bundle_libero_*.whl' \
  --build-arg LIBERO_THREE_ASSETS=dist/agent/libero-three-assets \
  -t REGISTRY/roborsi-libero-three-agent:REVISION .
```

最后一个 Docker stage 会再次加载全部 package map，校验 Long++ 12/12、Ultra 9/9、
PRO 80/40 和三套目录摘要，并实际加载固定 tokenizer。任何 bundle 未指向镜像内 tokenizer
都会使构建失败。约 49 MiB 的 ICL/tokenizer 构建输入进入镜像；模型权重和凭证不进入。

## 源码 smoke 与子集运行

Long++/Ultra-Long 单案例 smoke：

```bash
python benchmarks/libero_three_combined/run_source.py \
  --runtime-config ../work/libero_three/source-runtime.afs.json \
  --benchmark libero_long_plus_plus \
  --task t00-i01 \
  --results-root ../work/libero_three/source-smoke/longpp-t00 \
  --run-id longpp-t00-smoke \
  --port 19081
```

完整迁移子集：

```bash
python benchmarks/libero_three_combined/run_source_subset.py \
  --runtime-config ../work/libero_three/source-runtime.afs.json \
  --benchmark libero_long_plus_plus \
  --results-root ../work/libero_three/source-repro/longpp \
  --run-id longpp-v13-icl \
  --max-concurrent 4
```

将 `--benchmark` 换成 `libero_ultra_long` 或 `libero_pro` 即可。仓库 context map 是
权威案例列表，分别固定为 12、9、80。重复传 `--task` 可只跑 smoke，不需要另建任务列表。
三套都使用同一个 Benchmark service + canonical Agent runner；每个案例保留独立日志，
根目录生成含成功率和平均原生分数的 `summary.json`。预检和 runner 都会拒绝打开 VLA、
SAM3 或本地模型服务的主机配置。

标准 registry/镜像入口使用以下叶子 preset：

| Benchmark | Agent preset |
| --- | --- |
| Long++ | `robots/libero/agents/three_benchmark/long_plus_plus_v13.yaml` |
| Ultra-Long | `robots/libero/agents/three_benchmark/ultra_long_v13.yaml` |
| PRO | `robots/libero/agents/three_benchmark/pro.yaml` |

可移植运行时改用镜像内 bundle 名称，例如：

```bash
python benchmarks/libero_three_combined/run.py \
  --benchmark libero_long_plus_plus \
  --registry-root ../work/libero_three/registry \
  --agent-config bundle:libero_long_plus_plus_v13 \
  --agent-image REGISTRY/roborsi-libero-three-agent@sha256:DIGEST \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --results-root ../work/libero_three/results \
  --run-id longpp-v13-icl --dry-run
```

去掉 `--dry-run` 后执行。此模式不读取主机上的 ICL、tokenizer 或 Agent 源码。

只有 `success` 与原生 `task_failure` 是合法评测终态。Agent error、基础设施错误、缺少
`result.json` 或重复结果都会使命令失败。Smoke 的目标是验证链路，因此得到带完整证据的
`task_failure` 也表示运行链路通过，不代表任务得分成功。

## 输出与验收

每个案例应保存：

- `result.json`：RoboRSI 终态、1× 原生分数和固定 provenance；
- `native/score.json`：1× 快照、累计诊断及真实步数；
- `native/episode.mp4`：存在帧时的相机证据；
- `media/`：返回给 Agent 的内容寻址观测；
- `runner_trace/`：task/action/feedback envelope；
- Agent trace 与去除凭证值后的 `agent-config.json`。

验收要求计划数严格为 12、9、80，所有案例都有合法终态，无 Agent/基础设施错误，原生
证据可读，benchmark/source/config/package 哈希符合锁定值。模型工具可能非确定，因此
分数一致只是证据之一，不是唯一验收门槛。

## 镜像边界

Benchmark 镜像构建材料使用：

```bash
python -m benchmarks.package --benchmark libero_pro \
  --output ../work/libero_three/build-pro
python -m benchmarks.package --benchmark libero_lilo \
  --output ../work/libero_three/build-lilo
python -m benchmarks.libero_pro.assets \
  --source /path/to/full-evaluation/libero/libero \
  --output-dir ../work/libero_three/libero-pro-assets \
  --build-context ../work/libero_three/build-pro
```

构建上下文仍放在外部 `work/`。最终 Benchmark 镜像必须以 digest 固定；镜像只含
benchmark 和模拟器，不能含 Agent SDK、模型凭证或对话状态。Agent 的 ICL/tokenizer
只在独立 Agent 镜像中。当前条件不需要 Pi0.5/SAM3。

准备器仅密封 `bddl_files/` 与 `init_files/`，固定目录 SHA-256 为
`04ae2020acf89315108a68743f99f8fe9c4cb9fc47e67712298a25a7179d616a`，并把核验后的
snapshot 作为 `evaluation-assets/` 放入 PRO 构建上下文。Dockerfile 在提交镜像层前再次
核对同一摘要，并将其固定在 `/opt/libero-pro-evaluation`。两个镜像都会在可写 `/tmp`
中生成 LIBERO 路径配置，避免只读容器启动时写源码目录，也避免 PRO 回退到不完整的内置
评测文件。最终 PRO 镜像不再依赖 AFS、运行时资产挂载或在线下载；manifest 的
`assets_version` 直接记录镜像内资产摘要。

下表 ms-sc-01 已发布镜像记录历史交付，digest 保持原值。运行当前源码前，
须按 RoboRSI 接口和 `/roborsi/` 挂载重建镜像与 manifest。

| 角色 | 不可变镜像 |
| --- | --- |
| 三套评测共用 Agent | `registry.example.com/roborsi/ms-ccr/heart-libero-three-agent@sha256:33e4f5bd9947a208e83cbbbdc6b70297b0ebeb16893839ac2fb42fc627a1253e` |
| Long++ / Ultra-Long Benchmark | `registry.example.com/roborsi/ms-ccr/heart-libero-lilo@sha256:4e795cf962ff4680f88a757d4edba901440374e0c797246fc960221ba7822f81` |
| PRO Benchmark | `registry.example.com/roborsi/ms-ccr/heart-libero-pro@sha256:5fbf5694f17bd9500c1b495461e881464ecc29ebc26687d067b3c9a9a69606cf` |

三个镜像均已按 digest 拉取回验。三套 migration manifest 位于 Git 仓库外的
`../work/libero_three/registry-ms-ccr-v2/`，SHA-256 分别为 Long++
`e63ffac8da2776fca25093acf344b9f7984f8ceb716089cb0c60832023ef5141`、
Ultra-Long
`fd19a5c394d7556c22d2921744fd2e43541c7558821a3d42ab837f4d4f524fe8`、
PRO `9ca4dcfd0641fff9fe63727f9e74dc817258b87bbe7929e87b0972ecb8f5149a`。

上述 LiLo digest 还在本机 CPU 软件渲染、只读根文件系统下完成了 Long++ 原生协议探针：
持续 no-op 动作到 600 步 1x 边界，并生成原生 score、trace 和视频。该结果只验证
Benchmark 执行链路，不代表 Agent 任务准确率；Agent 成绩仅采用本文成绩章节中的真实
模型结果。

当前本机构建并校验的解压尺寸：

| 镜像 | 本地解压尺寸 |
| --- | ---: |
| `roborsi-libero-lilo`（Long++ 与 Ultra 共用） | 约 3.98 GB |
| `roborsi-libero-pro` | 约 4.85 GB |
| `roborsi-libero-three-agent` | 约 1.57 GB |

当前条件不需要历史 Pi0.5/SAM3 权重（原始合计约 10.9 GB），不要把它们打进镜像。

## 安全规则

- 不提交 `work/`、凭证、checkpoint、复制的 ICL、dataset、私有 registry manifest、
  视频和结果；ICL/tokenizer 副本仅作为 Agent 镜像输入；
- 参考评测目录只读；
- 报告中的源码 revision、配置 fingerprint、package 哈希和镜像 digest 必须不可变；
- Benchmark 服务拥有模拟器文件和原生分数，Agent 不得写入这些结果；
- adapter/scorer 变化后必须重新构建镜像并生成 manifest；源码模式也必须重新完成 smoke
  和依赖审计。

# 复现三套 LIBERO 评测

下方固定镜像属于历史交付，复现时需使用匹配的源码版本。当前 RoboRSI 要求重建镜像、
更新工厂并使用 `/roborsi/` 挂载；新运行请遵循
[迁移指南](source-zh/rst_source/usage/roborsi_migration.rst)。

本文说明如何在一台干净的 Linux 机器上运行已交付的 LIBERO-PRO、Long++
和 Ultra-Long 评测。原先从 m 集群读取的运行资产都已经封装进镜像：Benchmark
镜像包含模拟器、BDDL 和初始状态；共享 Agent 镜像包含三套 ICL 包、锁定的
tokenizer 和已安装 Agent bundle。镜像不包含模型权重和凭证。

## 准备条件

- Linux `x86_64`、Docker、Python 3.11；镜像解压后约占 10.4 GB，另需预留
  结果空间。
- 能访问 `registry.example.com/roborsi/ms-ccr`。
- 一个提供 `gpt-6-astra` 的 OpenAI Responses 兼容端点及 API key。
- 本仓库 PR 对应版本的 checkout。不需要 AFS 或 m 集群挂载。

本评测条件不运行本地 VLA 或 SAM3 模型，因此 GPU 不是模型依赖。交付的
manifest 默认申请一张 GPU，以提高 MuJoCo EGL 渲染速度和一致性；CPU 软件
渲染也能运行，但明显更慢，只建议用于小规模验证。

## 锁定镜像

```bash
export AGENT_IMAGE='registry.example.com/roborsi/ms-ccr/heart-libero-three-agent@sha256:33e4f5bd9947a208e83cbbbdc6b70297b0ebeb16893839ac2fb42fc627a1253e'
export LILO_IMAGE='registry.example.com/roborsi/ms-ccr/heart-libero-lilo@sha256:4e795cf962ff4680f88a757d4edba901440374e0c797246fc960221ba7822f81'
export PRO_IMAGE='registry.example.com/roborsi/ms-ccr/heart-libero-pro@sha256:5fbf5694f17bd9500c1b495461e881464ecc29ebc26687d067b3c9a9a69606cf'

docker pull "$AGENT_IMAGE"
docker pull "$LILO_IMAGE"
docker pull "$PRO_IMAGE"
```

## 单镜像部署

只能为每个作业指定一个镜像的调度平台，可使用
[`benchmarks/libero_three_combined/`](../benchmarks/libero_three_combined/README.md)
中的合成配方。已发布的不可变镜像为：

```bash
export LONGPP_COMBINED_IMAGE='ghcr.io/opensensenova/sensenova-roborsi-libero-long-plus-plus@sha256:814139261e914b114cb89a359c6a39d4f409a556f79928e986b6ade3dfe7dc7a'
export ULTRA_COMBINED_IMAGE='ghcr.io/opensensenova/sensenova-roborsi-libero-ultra-long@sha256:814139261e914b114cb89a359c6a39d4f409a556f79928e986b6ade3dfe7dc7a'
export PRO_COMBINED_IMAGE='ghcr.io/opensensenova/sensenova-roborsi-libero-pro@sha256:a83417f1459a4c555c457caa82ef00a5de50191e3d8deb943894fa9285cff172'
```

Long++ 和 Ultra-Long 按规范使用独立 GHCR Package，但二者有意复用完全相同的
LiLo+Agent 镜像内容；PRO 使用 PRO+Agent 镜像。镜像内包含 Benchmark、Agent bundle、ICL 和 tokenizer；运行时只需
模型 endpoint、只读 API key 文件和可写结果目录。由于凭证和 Benchmark 同容器，该模式
隔离性弱于标准双容器部署。

覆盖 entrypoint 即可执行固定子集：

```bash
docker run --rm --gpus all \
  --entrypoint python \
  -v /path/to/model_api.key:/run/secrets/model_api.key:ro \
  -v "$RUN_ROOT/results:/results" "$LONGPP_COMBINED_IMAGE" \
  -B /opt/roborsi/benchmarks/libero_three_combined/run_combined_subset.py \
  --benchmark libero_long_plus_plus --run-id longpp-subset \
  --results-root /results/longpp-subset --max-concurrent 16 --gpu-count 1 \
  --api-key-file /run/secrets/model_api.key \
  --base-url https://your-responses-endpoint.example/v1
```

Long++ 和 Ultra-Long 共用 `LILO_IMAGE`，由 manifest 选择服务；PRO 使用
`PRO_IMAGE`。三者共用 `AGENT_IMAGE`，每次评测选择其中一个已安装 bundle。

## 安装 Runner

在仓库根目录执行：

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

可以使用机器已配置的内部 pip 源；这不会改变容器内的锁定依赖。

## 生成本地 Benchmark registry

manifest 由对应的 Benchmark 镜像直接生成，保证运行时身份、任务列表和镜像
digest 一致。

```bash
export RUN_ROOT="$PWD/../work/libero-three-reproduction"
mkdir -p "$RUN_ROOT/registry/libero_long_plus_plus" \
  "$RUN_ROOT/registry/libero_ultra_long" \
  "$RUN_ROOT/registry/libero_pro" \
  "$RUN_ROOT/results"

docker run --rm --entrypoint python \
  -v "$RUN_ROOT/registry:/output" "$LILO_IMAGE" \
  -m benchmarks.libero_lilo.manifest \
  --image "$LILO_IMAGE" --benchmark libero_long_plus_plus \
  --profile migration_subset \
  --output /output/libero_long_plus_plus/manifest.json

docker run --rm --entrypoint python \
  -v "$RUN_ROOT/registry:/output" "$LILO_IMAGE" \
  -m benchmarks.libero_lilo.manifest \
  --image "$LILO_IMAGE" --benchmark libero_ultra_long \
  --profile migration_subset \
  --output /output/libero_ultra_long/manifest.json

docker run --rm --entrypoint python \
  -v "$RUN_ROOT/registry:/output" "$PRO_IMAGE" \
  -m benchmarks.libero_pro.manifest \
  --image "$PRO_IMAGE" --profile migration_subset \
  --output /output/libero_pro/manifest.json
```

预期任务数分别为 Long++ 12、Ultra-Long 9、PRO 80。在调用模型前先验证完整
执行计划：

```bash
export OPENAI_API_KEY='replace-me'
export OPENAI_BASE_URL='https://your-responses-endpoint.example/v1'

python benchmarks/libero_three_combined/run.py \
  --benchmark libero_long_plus_plus \
  --registry-root "$RUN_ROOT/registry" \
  --agent-config bundle:libero_long_plus_plus_v13 \
  --agent-image "$AGENT_IMAGE" \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --results-root "$RUN_ROOT/results" --run-id longpp-plan --dry-run

python benchmarks/libero_three_combined/run.py \
  --benchmark libero_ultra_long \
  --registry-root "$RUN_ROOT/registry" \
  --agent-config bundle:libero_ultra_long_v13 \
  --agent-image "$AGENT_IMAGE" \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --results-root "$RUN_ROOT/results" --run-id ultra-plan --dry-run

python benchmarks/libero_three_combined/run.py \
  --benchmark libero_pro \
  --registry-root "$RUN_ROOT/registry" \
  --agent-config bundle:libero_pro \
  --agent-image "$AGENT_IMAGE" \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --results-root "$RUN_ROOT/results" --run-id pro-plan --dry-run
```

key 和 endpoint 只会传给隔离的 Agent 容器，不会传给 Benchmark 容器，也不会
写入命令参数、manifest 或结果记录。

## 运行真实模型小样本

先运行一个代表性 case。下面是实际 Agent 评测，不是固定动作或 no-op 模拟器
检查。

```bash
bench eval \
  --registry-root "$RUN_ROOT/registry" \
  --results-root "$RUN_ROOT/results" --run-id longpp-one-case \
  --agent-config bundle:libero_long_plus_plus_v13 \
  --agent-image "$AGENT_IMAGE" \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --benchmark libero_long_plus_plus \
  --task libero_long_plus_plus:t00-i01 --seed 0 \
  --max-concurrent 1 --case-timeout-s 86400
```

Ultra-Long 使用 bundle `libero_ultra_long_v13`、benchmark
`libero_ultra_long` 和 task `libero_ultra_long:t00-i01`。PRO 使用 bundle
`libero_pro`、benchmark `libero_pro` 和 task
`libero_pro:libero_spatial_task-t00-i03`。

## 运行三个迁移子集

去掉上述三条计划命令中的 `--dry-run`，使用新的 run ID，并按可用模拟器容量
设置并发。例如：

```bash
python benchmarks/libero_three_combined/run.py \
  --benchmark libero_long_plus_plus \
  --registry-root "$RUN_ROOT/registry" \
  --agent-config bundle:libero_long_plus_plus_v13 \
  --agent-image "$AGENT_IMAGE" \
  --agent-credential-env OPENAI_API_KEY \
  --agent-credential-env OPENAI_BASE_URL \
  --results-root "$RUN_ROOT/results" --run-id longpp-full \
  --max-concurrent 1 --case-timeout-s 86400
```

再按上面的 benchmark/bundle 对运行 Ultra-Long 和 PRO。主 1x 分数不要启用
`plus9_on_failure`。只有在锁定输入完全不变时，才可用新的 run ID 配合
`--resume-from OLD_RUN_ID`。

## 验证输出

每个完成的 case 都应包含 `result.json`、`native/score.json`、有图像时生成的
原生视频、`runner_trace/`、media 和完整 Agent trace。只有 `success` 和原生
`task_failure` 是有效评测终态；基础设施错误或 Agent 错误都不是分数。计划
case 数应为 12、9 和 80。

已记录的真实模型证据及其严格限制见
[`README.zh-CN.md`](README.zh-CN.md)。特别是
PRO 的 786/800 是条件对齐的完整集参考结果，不是本仓库 fixed-state-3 的
80-case 子集新跑成绩。
