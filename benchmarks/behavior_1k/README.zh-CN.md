# BEHAVIOR-1K

[English](README.md) · [全部指南](../../docs/README.md)

本接入通过通用 Benchmark 服务与 Runner 提供 BEHAVIOR-1K 评测，包含原生任务检查、
独立模拟器进程、官方 21 维动作接口、RGB-D 观测与原生评分。

## 任务、动作与评分

原生源码固定为 BEHAVIOR-1K v3.9.2，commit
`b1979916ec1549b10a4e65e630bc6504a9af1b00`。
[任务列表](official_tasks.json)包含 100 个任务。生成 catalog 时逐个原生 reset，
读取实际任务指令与步数上限。服务提供该 catalog 中的任务，使用 `public_test`
instance 301（public-test index 0）、seed 0。

每次动作格式为 `{"action": [...]}`，必须包含恰好 21 个有限数值，依次为：

| 维数 | 控制内容 |
| --- | --- |
| 3 | 底盘速度 |
| 4 | 躯干关节目标 |
| 6 | 左末端在底盘坐标系下的位置与旋转向量 |
| 1 | 左夹爪 |
| 6 | 右末端在底盘坐标系下的位置与旋转向量 |
| 1 | 右夹爪 |

动作必须符合原生边界；适配器拒绝越界值，不裁剪或归一化。观测包含全分辨率头部、
双腕 RGB/depth PNG、公开的本体状态和动作边界。Depth 图像使用 0.01–10 m 范围、
3.5 m 偏移的反向对数强度编码，像素值为显示强度，不是米制距离。

成功由原生 `task.success` 决定，分数来自官方聚合的 `q_score.final`。
显式停止在当前状态评分，不推进物理。原生 step 或 metric 失败报告为基础设施错误。
每个 episode 独占模拟器进程，并有清理时限。

## 环境与镜像

使用 Linux x86_64、Python 3.11、Docker、支持的 NVIDIA 驱动和 NVIDIA Container
Toolkit。仿真需要 RTX 级 GPU，建议 24 GB 显存。准备 32 GB 内存、至少 80 GB
空闲构建空间，并另外预留授权资产及其快照的空间。

[构建锁](build-lock.json)固定上游 `linux/amd64` 镜像，压缩后约 14.7 GB。
Dockerfile 安装固定版本的原生源码和带哈希的服务依赖；镜像记录原生依赖清单与构建证据。

在仓库根目录安装 Agent 与评测器：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[runtime]'
```

将 `BEHAVIOR_DELIVERY` 设为源码目录外的绝对路径，路径中不包含符号链接。
将 `BEHAVIOR_IMAGE_TAG` 设为你有发布权限的容器仓库中的新 tag。使用新的构建目录：

```bash
mkdir -p "$BEHAVIOR_DELIVERY"
BEHAVIOR_BUILD="$BEHAVIOR_DELIVERY/build"
python -m benchmarks.package --benchmark behavior_1k --output "$BEHAVIOR_BUILD"
python "$BEHAVIOR_BUILD/build_image.py" --tag "$BEHAVIOR_IMAGE_TAG"
```

登录容器仓库后发布本次构建，并读取实际摘要：

```bash
docker push "$BEHAVIOR_IMAGE_TAG"
docker pull "$BEHAVIOR_IMAGE_TAG"
BEHAVIOR_IMAGE=$(docker image inspect "$BEHAVIOR_IMAGE_TAG" --format '{{index .RepoDigests 0}}')
```

后续命令均使用本次构建的实际 `repository@sha256:digest`。上游 base digest
仅标识基础环境。将导出的 `source.json`、`build.json`、`build-lock.json`
和最终镜像摘要保存在部署记录中。

## 资产、catalog 与 registry

通过上游授权安装流程获取资产与 key。将 `BEHAVIOR_DATA` 设为包含以下内容的私有资产目录：

```text
behavior-1k-assets/
omnigibson-robot-assets/
2026-challenge-task-instances/
omnigibson.key
```

Key 保存在私有资产挂载中。资产准备会复制整个目录并计算快照哈希，需为两份数据预留空间。
在仓库根目录执行：

```bash
python -m benchmarks.behavior_1k.prepare assets \
  --source "$BEHAVIOR_DATA" \
  --output-dir "$BEHAVIOR_DELIVERY/registry/behavior_1k/assets"
BEHAVIOR_SNAPSHOT=$(python -c \
  'import json, sys; print(json.load(open(sys.argv[1]))["path"])' \
  "$BEHAVIOR_DELIVERY/registry/behavior_1k/assets/asset.json")
```

在刚构建的镜像中生成 catalog。以下命令启动原生模拟器，对 `sorting_vegetables`
执行 reset。重复 `--task` 可添加 100 个任务列表中的其他任务。Catalog 和 work
目录必须尚不存在。

```bash
docker run --rm --gpus all \
  --mount type=bind,src="$BEHAVIOR_SNAPSHOT",dst=/roborsi/assets/behavior_1k,readonly \
  --mount type=bind,src="$BEHAVIOR_DELIVERY",dst=/delivery \
  "$BEHAVIOR_IMAGE" python -m benchmarks.behavior_1k.prepare catalog \
  --task sorting_vegetables \
  --output-dir /delivery/registry/behavior_1k/catalog \
  --work-dir /delivery/catalog-work
```

从同一镜像读取运行时标识，再生成 manifest：

```bash
docker run --rm \
  --mount type=bind,src="$BEHAVIOR_DELIVERY",dst=/delivery \
  "$BEHAVIOR_IMAGE" python -m benchmarks.behavior_1k.prepare runtime-info \
  --output /delivery/runtime-info.json

python -m benchmarks.behavior_1k.prepare manifest \
  --image "$BEHAVIOR_IMAGE" \
  --assets "$BEHAVIOR_SNAPSHOT" \
  --catalog "$BEHAVIOR_DELIVERY/registry/behavior_1k/catalog" \
  --runtime-info "$BEHAVIOR_DELIVERY/runtime-info.json" \
  --output "$BEHAVIOR_DELIVERY/registry/behavior_1k/manifest.json"
```

最终目录结构为：

```text
registry/behavior_1k/
  assets/
    asset.json
    snapshots/<sha256>/
  catalog/catalog.json
  manifest.json
```

资产与 catalog 必须位于 manifest 目录内部，路径不包含上级跳转或符号链接。
Manifest 记录相对路径与哈希、镜像摘要和实际检查过的任务。Registry 启动时，
快照挂载至 `/roborsi/assets/behavior_1k`，catalog 挂载至
`/roborsi/assets/behavior_1k-catalog`。

## 使用 Agent 评测

在 Agent 环境中设置 `OPENAI_API_KEY`，选择支持视觉与工具调用的模型。
通用预设接收任务、21 维动作 schema 与 RGB-D 观测：

```bash
bench eval --registry-root "$BEHAVIOR_DELIVERY/registry" \
  --results-root "$BEHAVIOR_DELIVERY/results" --run-id behavior-1 \
  --benchmark behavior_1k --task behavior_1k:sorting_vegetables --seed 0 \
  --agent-config configs/agents/embodied/default.yaml \
  --agent-set 'runtime.llm.model="YOUR_VISION_TOOL_MODEL"' \
  --agent-set 'agent.action_timeout_s=900' \
  --timeout-s 900 --case-timeout-s 7200
```

原生任务步数来自 catalog；Agent 轮数限制与 Runner 超时分别控制。
预算、产物与恢复见 [Agent 配置](../../docs/agents.zh-CN.md)和
[评测指南](../../docs/evaluation.zh-CN.md)，离线检查见[测试指南](../../tests/README.md)。

原生模拟器、机器人资产与数据集遵循各自的上游许可证及访问条款。
