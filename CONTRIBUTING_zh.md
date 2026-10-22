# 贡献指南

[English](CONTRIBUTING.md)

本次发布包含 Agent 运行时与 LIBERO 系列、Bench2Dex、DexJoCo、BEHAVIOR-1K 和 RoboCasa365 的 benchmark 评测。
请围绕该范围提交改动，并保持现有接口契约。

1. 修改前核对实际 Git remote、分支和 upstream，阅读接口实现与两侧调用方。
2. 从用户需要观察的信息与控制的行为出发。将框架机制与可替换的 Agent 策略分开，
   复用已有配置、RPC、运行时和产物管理工具。
3. 原生 benchmark 行为放在 `robots/<benchmark>/`。在使用处导入模拟器与模型依赖，
   使基础包导入和 CLI help 不要求安装原生栈。
4. 遵循邻近代码的类型、Google 风格 docstring 与项目日志约定；在输入所属边界校验，
   明确资源清理责任。
5. 尽量复用 fixture 验证可观察行为。用户行为改变时，同时更新 `docs/` 下的中英文指南。

## 开发环境与检查

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[runtime,test]'
python -m pip install pre-commit==4.6.2
pre-commit install
pre-commit run --all-files
pytest tests/unit_tests -q
```

原生可选检查见 [tests/README.md](tests/README.md)。必须通过的 CI 在 Linux 上使用
Python 3.11 和 3.12 运行离线单元测试，不依赖模型服务、模拟器、资产下载或 GPU。

## Pull request

开发 PR 面向实际目标仓库的 `main`。提交 PR 前，fetch 对应 remote，将功能分支
rebase 到最新 `main`，然后重新执行相关检查。按功能组织改动，一个 PR 可包含多个提交。
提交信息使用 Conventional Commits，例如 `fix(evaluation): preserve native score after cleanup`。

说明用户可见变化、兼容性与迁移要求，以及实际运行过的检查。区分离线集成与原生模拟器
或模型任务成功。发布前检查完整 diff。

不要削弱失败测试以换取通过。不要提交凭据、本地部署配置、日志、模型权重、下载资产
或生成结果。保留原有许可证与归属声明。
