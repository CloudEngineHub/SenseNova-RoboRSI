# 快速开始

[English](getting-started.md) · [全部指南](README.md)

Agent 和评测器使用 Python 3.10–3.12。原生 benchmark 镜像运行于 Linux，
并安装各自固定的依赖。连接已有 HTTP benchmark 服务时，无需在本机安装模拟器。

## 安装

在仓库根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[runtime,test]'
bench --help
```

Windows 使用 `.venv\Scripts\Activate.ps1` 激活环境。公开 CI 和原生 benchmark
构建说明面向 Linux。单元测试使用本地替身，不调用模型服务或启动模拟器。

```bash
pytest tests/unit_tests -q
```

## 准备 benchmark

选择 [LIBERO](../benchmarks/libero/README.md)、
[LIBERO-PRO](../benchmarks/libero_pro/README.md)、
[Long++ / Ultra-Long](../benchmarks/libero_lilo/README.md) 或
[DexJoCo](../benchmarks/dexjoco/README.zh-CN.md)，按对应说明构建镜像、
获取所需资产，并在本地 registry 目录写入 manifest。Manifest 记录镜像摘要、任务、
种子、动作协议、评测步数及原生评分规则。

LIBERO-PRO 需要另外获取完整的评测资产目录，且校验和必须符合构建说明。
本仓库不提供这份数据或自动下载入口。完成源码安装并不代表已经具备运行 PRO 的资产。

## 检查评测流程

按 LIBERO 构建说明准备好 registry 后，运行固定动作示例：

```bash
bench eval --registry-root /absolute/path/to/registry \
  --results-root /absolute/path/to/results --run-id hold-1 \
  --benchmark libero --task libero:0 --seed 0 \
  --agent-factory examples.roborsi.hold_agent:make_agent \
  --agent-version hold-example-v1 --timeout-s 180 --case-timeout-s 900
```

Agent 会读取全部相机文件并保持夹爪打开。预期原生任务得分为失败；该检查验证通信和
结果记录，不代表具备任务求解能力。用 `bench status --results-root
/absolute/path/to/results --run-id hold-1` 查看 case 状态。

## 运行模型 Agent

在环境中设置 `OPENAI_API_KEY`。使用兼容的自定义服务时，再设置 `OPENAI_BASE_URL`。
将 [`default.yaml`](../configs/agents/embodied/default.yaml) 中的模型占位符替换为
支持视觉与工具调用的模型，或在命令行覆盖：

```bash
bench eval --registry-root /absolute/path/to/registry \
  --results-root /absolute/path/to/results --run-id model-1 \
  --benchmark libero --task libero:0 --seed 0 \
  --agent-config configs/agents/embodied/default.yaml \
  --agent-set 'runtime.llm.model="YOUR_VISION_TOOL_MODEL"' \
  --timeout-s 180 --case-timeout-s 3600
```

连接已有 HTTP 服务时，将 `--registry-root ...` 替换为
`--benchmark-url libero=https://benchmark.example`。如果服务需要鉴权，
在环境变量中设置令牌，并添加 `--benchmark-token-env ROBORSI_BENCHMARK_TOKEN`。

上下文和执行预算见 [Agent 配置](agents.zh-CN.md)；结果、并发与恢复见
[评测指南](evaluation.zh-CN.md)。
