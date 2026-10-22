# 构建 RoboCasa365 benchmark 镜像

[English](BUILD.md) · [Benchmark 指南](README.zh-CN.md)

Dockerfile 在已有 Target50 环境上构建，默认基础镜像为：

```text
ghcr.io/opensensenova/sensenova-roborsi-robocasa365@sha256:8494fef17ee5979a072967632a2cb6ca885a165e87b01fb88d40c9f88b5b82e1
```

源交付将该 GHCR package 标为私有。构建前需要获得授权拉取权限，也可通过已有的
`ROBOCASA365_BASE_IMAGE` 参数提供兼容基础镜像。Digest 标识镜像内容，不授予
registry 访问权限。本仓库暂未包含从公开输入独立、完整重建该基础镜像的配方。

## 原生基础环境契约

基础镜像为 Linux amd64，压缩体积约 25.94 GB，提供以下内容：

| 路径 | 所需内容 |
| --- | --- |
| `/opt/rpent-py310` | Python 3.10.21、Torch 2.7.0+cu126、MuJoCo 3.3.1 及固定版本的 RoboCasa/robosuite/RLDX 包 |
| `/opt/robocasa-assets` | RoboCasa commit `2692d8fc5fd86708a1b2028dcbce892ec418a9e7` 对应的厨房资产 |
| `/opt/rldx/RLDX-1-FT-RC365` | revision `587e9ecdcc5e7184fcc17f58713908edff5af041` 的 RLDX-1 权重 |
| `/opt/hf-cache` | revision `4b9f870d1287e0d38d7eb1445e6d8c60afe66dd7` 的 RLDX VLM 配置 |
| `/opt/heart-robocasa/BUILD` | 原基础镜像环境记录 |

基础镜像提供 OSMesa/EGL/GL 系统库，以及 `RLDX_CHECKPOINT`、模拟器资产位置等
运行配置。替代基础镜像需提供兼容的路径、包、资产、权重与环境变量。
Dockerfile 清理步骤还要求 `/opt/heart-robocasa` 目录存在。

[`requirements.txt`](requirements.txt) 保留原镜像解析后的 Python 环境。
它是环境记录，不是最小依赖 lock，也不是独立基础镜像构建配方。
Dockerfile 继承这些包，不会安装该文件。原生源码版本还记录于
[`target50.json`](../../robots/robocasa/eval/target50.json)。

## 导出与构建

在已安装框架的源码 checkout 中，导出到新目录：

```bash
python -m benchmarks.package --benchmark robocasa365 \
  --output work/robocasa365/build
docker login ghcr.io
docker build --platform linux/amd64 -t robocasa365:local work/robocasa365/build
export ROBOCASA365_IMAGE=robocasa365:local
```

`docker login` 使用你已获授权的 registry 凭据。不要把凭据写入构建参数或源码。
使用自有兼容基础镜像时：

```bash
docker build --platform linux/amd64 \
  --build-arg ROBOCASA365_BASE_IMAGE="$YOUR_COMPATIBLE_BASE_DIGEST" \
  -t robocasa365:local work/robocasa365/build
```

`build-inputs.json` 在标准 Docker 文件外声明 `agent-packages.txt`。
镜像卸载继承的 Agent 分发包，删除旧应用并保留其 `BUILD` 记录，
然后仅复制已声明的 benchmark 运行源码。原生 RLDX 代码与权重继续保留，
因为操作工具需要调用它们。`verify_benchmark_runtime` 检查导出的源码边界，
并拒绝继承的 Agent 包。

将导出的 `source.json` 和 `build.json` 与构建证据一并保存。
基础镜像 digest 和先前交付 digest 均不是本次重建镜像的 digest。
推送自有镜像 tag 后，通过
`docker image inspect YOUR_IMAGE_TAG --format '{{json .RepoDigests}}'`
取得 repository digest，Registry 注册时使用该准确值。参见
[README.zh-CN.md](README.zh-CN.md)。

## 验证

无需 Docker、模型凭据或模拟器依赖即可检查构建上下文导出与服务源码导入。
离线覆盖包括：

```bash
pytest tests/unit_tests/roborsi/benchmarks/test_robocasa365_registration.py \
  tests/unit_tests/robots/robocasa/test_runtime_bundle.py \
  tests/unit_tests/robots/robocasa/test_roborsi_adapter.py \
  tests/unit_tests/robots/robocasa/test_score.py -v
```

真实镜像构建仍需要基础镜像与容器工具。原生验收还需要授权资产、权重和兼容 GPU
宿主机。源码导出与使用假 toolkit 的离线测试不证明原生任务成功。
先前镜像的验收记录不代表本次重建已通过验证。
