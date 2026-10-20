# Bench2Dex benchmark

[English](README.md)

本接入通过 RoboRSI 通用 benchmark HTTP 接口提供固定的 26 个 Bench2Dex 任务，
保留原生动作、相机标定、控制预算、样本索引映射、终止、评分和清理语义。
Agent 策略通过标准评测接口单独提供。

原生运行需要 Linux x86-64、受支持的 NVIDIA RTX GPU 及驱动、支持 GPU 的
Docker，以及固定 Isaac Sim 镜像和上游仓库的访问权限。镜像使用 Isaac Sim、
Isaac Lab 和 Bench2Dex，分别适用其许可与访问要求。资产单独下载。
自定义参考 harness 采用
[Apache-2.0](../../robots/bench2dex/reference/LICENSE_NOTICE.md) 许可证。
本次迁移不构成原生任务成功或模型性能的验证。

## 准备外部资产

安装框架后，从仓库根目录执行以下命令。资产下载命令需要 `huggingface_hub`。

```bash
python -m pip install huggingface_hub
python -m benchmarks.bench2dex.assets --download \
  --source work/bench2dex/download --output work/bench2dex/assets
python -m benchmarks.bench2dex.prepare catalog \
  --assets work/bench2dex/assets --sample 5 \
  --output work/bench2dex/catalog.json
```

资产工具从官方 `Bench2Dex/Assets` 数据集的固定版本
`bf65215f844d1fca30750e4cc70d7266650abf0a` 选择文件。复制前验证 Git/LFS 对象，
复制后逐文件校验，并在旁边写出文件清单和目录校验值。验证已有下载时省略
`--download`。评测期间保持封存资产和 catalog 只读。

重复 `--sample` 可选择更多原生 episode 索引，重复 `--task` 可选择
`robots/bench2dex/tasks.json` 中的任务。评测的 `--seed` 映射到该 episode 索引；
原生 RNG seed 由 `protocol.json` 固定。使用 `--smoke-steps 4` 生成的 catalog
用于诊断，会明确标记为不具备正式评分资格。

## 构建与注册

```bash
python -m benchmarks.package --benchmark bench2dex \
  --output work/bench2dex/build
python -m benchmarks.bench2dex.build \
  --context work/bench2dex/build --tag YOUR_REGISTRY/bench2dex:BUILD \
  --evidence work/bench2dex/build-evidence --publish
export ROBORSI_BENCH2DEX_IMAGE=$(docker image inspect YOUR_REGISTRY/bench2dex:BUILD \
  --format '{{index .RepoDigests 0}}')
python -m benchmarks.bench2dex.prepare manifest \
  --image "$ROBORSI_BENCH2DEX_IMAGE" --assets work/bench2dex/assets \
  --catalog work/bench2dex/catalog.json \
  --output work/bench2dex/registry/bench2dex/manifest.json
```

将 `YOUR_REGISTRY` 和 `BUILD` 替换为自己的镜像仓库与标签。Dockerfile 固定
模拟器基础镜像和原生源码版本。导出的构建上下文包含声明的 benchmark 依赖闭包
和构建输入。构建工具在发布前检查依赖与源码导入，再按 digest 拉取并校验镜像。
只做本地构建时省略 `--publish`；manifest 需要带仓库 digest 的镜像引用。
这些检查不执行 GPU episode。

生成的 manifest 含操作者本地资产路径。manifest、下载数据、凭据和生成的证据
应保存在发布源码之外。

## 使用 Agent 评测

按 [Agent 指南](../../docs/agents.zh-CN.md) 配置模型和凭据，然后使用标准预设
或自己的 Agent：

```bash
bench eval --registry-root work/bench2dex/registry \
  --benchmark bench2dex --task bench2dex:26 --seed 5 \
  --agent-config configs/agents/embodied/default.yaml \
  --results-root work/bench2dex/results --run-id bench2dex-1 \
  --timeout-s 900 --case-timeout-s 86400 --max-concurrent 1
```

该预设用于演示通用接口，不是复现策略。请为实际运行设置模型、上下文和决策预算。
动作使用有限数值的绝对关节位置目标：`{"actions": [[...], ...]}`，每个动作的
维度与活跃关节数一致。上一动作块仍有剩余动作时使用 `{"continue": true}`。
Agent 可见 RGB 图像和经过标定的机器人信息；原生成功状态和评分详情仅在结束
case 时返回。

若自行管理原生环境，配置 `BENCH2DEX_ROOT`、`ISAACLAB_ROOT`、
`ISAACLAB_PYTHON`、`BENCH2DEX_ASSETS` 和 `BENCH2DEX_CATALOG`。
原生 Bench2Dex checkout 旁的 `dex2bench_dataset` 链接必须指向封存资产。
启动通用服务：

```bash
python -m roborsi.evaluation.service_host --kind benchmark \
  --factory robots.bench2dex.benchmark_service:make_bench2dex_benchmark \
  --host 127.0.0.1 --port 8000
```

随后将评测命令的 `--registry-root` 替换为
`--benchmark-url bench2dex=http://127.0.0.1:8000`。
结果、状态查询和恢复见 [评测指南](../../docs/evaluation.zh-CN.md)。
离线测试覆盖模拟原生提供方、HTTP 传输、构建边界和可重试清理，不代表该模拟器
镜像已完成 GPU 验证。
