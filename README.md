<h1 align="center">SenseNova-RoboRSI: Recursive Self-Improvement for Embodied Agents</h1>

<p align="center"><strong>Build, evaluate, and improve embodied agents with a shared runtime.</strong></p>

<p align="center">
  <img src="assets/badges/python.svg" alt="Python 3.10–3.12" />
  <img src="assets/badges/license.svg" alt="License: Apache 2.0" />
  <img src="assets/badges/status.svg" alt="Status: Pre-Alpha" />
</p>

<p align="center">
  <a href="https://www.sensenova.ai/has-gpt-6-astra-achieved-embodied-intelligence"><img src="assets/badges/report.svg" alt="Report: Has GPT-6 Achieved Embodied Intelligence?" /></a>
  <a href="https://huggingface.co/sensenova/sensenova-roborsi-27b-preview"><img src="assets/badges/model.svg" alt="Model: SenseNova-RoboRSI-27B-Preview" /></a>
</p>

<p align="center">
  <strong>English</strong> · <a href="README.zh-CN.md">简体中文</a> ·
  <a href="#quick-start">Quick Start</a> · <a href="docs/README.md">Docs</a> ·
  <a href="https://www.sensenova.ai/has-gpt-6-astra-achieved-embodied-intelligence">Report</a> ·
  <a href="#benchzoo">BenchZoo</a> ·
  <a href="#harness-results">Harness Results</a> ·
  <a href="#sensenova-roborsi-27b-preview">RoboRSI-27B-Preview</a> ·
  <a href="#release-plan--roadmap">Release plan</a>
</p>

## News

- **2026-10-16** — Initial code and usage guides for **LIBERO, LIBERO-PRO, LIBERO-Long++ and LIBERO-Ultra-Long** are available in this branch. See the [getting started guide](docs/getting-started.md).

- **2026-10-16** — SenseNova-RoboRSI has been used in the empirical report [**Has GPT-6 Achieved Embodied Intelligence?**](https://www.sensenova.ai/has-gpt-6-astra-achieved-embodied-intelligence).
- **2026-10-16** — [**🤗 SenseNova-RoboRSI-27B-Preview**](https://huggingface.co/sensenova/sensenova-roborsi-27b-preview) now runs across different environments, including on real robots and in simulation! The open-weight release is expected on **October 20, 2026**, with the technical report to follow.

- **2026-10-09** — SenseNova-RoboRSI achieves an **average score of 60.08** and a **success rate of 54.17%** on RoboDojo, a gain of **+31.11 points** over the GPT-6 Astra baseline (**28.97**). Results are being submitted to the official RoboDojo leaderboard. See [Harness Results](#harness-results) for benchmark comparisons.

## Contributors

- **Project leads:** Hanming Deng, Zhongang Cai, Haiwen Diao, Zhi Hou, Zhonghua Wu, Qingyi Tao
- **Model team:** Silei Wu\*, Weiye Xu, Bo Liu, Pengfei Liu, Tailai Chen, Chenjing Ding, Jiahao Wang, Changxu Wei, Zongpu Zhang
- **Harness team:** Jiapeng Luo\*, Yuyao Shao, Linjun Dai, Quanzhou Li, Ziyi Shang, Wanqi Yin, Xiaowan Li, Donghao Wu, Tianbo Zhong
- **Advisor:** Dahua Lin, Xiaogang Wang, Ziwei Liu, Lewei Lu, Lei Yang

\* denotes team leads.

## Overview

Connect your model, skills, and robot tools through a shared runtime, customize
prompts and context, and evaluate policies in environments that retain their
native execution and scoring logic.

On top of this runtime, **recursive self-improvement (RSI)** uses execution
traces and task feedback to improve the Harness while keeping model parameters
fixed. Candidate changes are retested, and validated improvements are carried
into the next agent version, connecting task execution with continuous improvement.

🎉 **[SenseNova-RoboRSI-27B-Preview](#sensenova-roborsi-27b-preview)** extends this work to model training. Validated
interaction experience becomes multimodal supervision for goal understanding,
action decisions, and feedback-based correction. Updated models return to the
same runtime for evaluation and further exploration, connecting model training
and Harness improvement through shared experience and joint retesting.

<p align="center">
  <img src="assets/sensenova-roborsi-overview-en.webp" alt="SenseNova-RoboRSI agent interfaces, execution loop, benchmark integration, and RSI workflow" width="75%" />
</p>

### Core capabilities

#### Harness: A shared runtime

- **Flexible agent interfaces.** Connect models, prompts, skills, and tools/MCP;
  configure context and caching to suit each task.
- **Unified execution and evaluation.** Run VLA skills, scripted actions, or
  end-effector tools across benchmarks with native feedback and scoring.
- **Experiment records and training data.** Record full traces, export training
  episodes, and run batch evaluations with concurrency and recovery.

#### RSI: Continuous Harness improvement

- **Learn from execution feedback.** Refine action prediction, planning,
  feedback, and memory organization while keeping model parameters fixed.
- **Retest and retain improvements.** Track agent versions, evaluate candidate
  changes under the same task conditions, and carry validated improvements forward.

## Quick Start

Use Python 3.10–3.12 for the Agent and evaluator. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[runtime,test]'
bench --help
```

On Windows, activate with `.venv\Scripts\Activate.ps1`.

Follow the [installation and first evaluation guide](docs/getting-started.md)
to prepare a benchmark and run a fixed-action or model Agent. Native benchmark
images target Linux; connecting to an existing HTTP benchmark requires no local
simulator installation.

- **Benchmark setup:** [LIBERO](benchmarks/libero/README.md),
  [LIBERO-PRO](benchmarks/libero_pro/README.md), and
  [LIBERO-Long++ / LIBERO-Ultra-Long](benchmarks/libero_lilo/README.md).
- **Agent configuration:** [Models, prompts, context and budgets](docs/agents.md).
- **Evaluation:** [Batch execution, results and resume](docs/evaluation.md).

## BenchZoo

Available Agent methods and upcoming releases by benchmark. The released LIBERO
entries share configurable EmbodiedAgent presets; select your model in the
preset and follow the corresponding benchmark directory for setup and evaluation.

| Benchmark | Status |
| --- | --- |
| RoboDojo | Coming soon |
| [LIBERO-Pro](benchmarks/libero_pro/) | Released |
| [LIBERO-Long++](benchmarks/libero_lilo/) | Released |
| [LIBERO-Ultra-Long](benchmarks/libero_lilo/) | Released |
| RoboLab | Coming soon |
| Bench2Dex | Coming soon |
| DexJoCo | Coming soon |
| LHVLN | Coming soon |
| VLN-CE | Coming soon |
| SIMPLE | Coming soon |
| BEHAVIOR-1K | Coming soon |

## Harness Results

Each table shows SenseNova-RoboRSI alongside selected reference results. Higher is better.

### [RoboDojo](https://robodojo-benchmark.com/)

On RoboDojo-Sim, SenseNova-RoboRSI achieves an **average score of 60.08** and a
**success rate of 54.17%**. Compared with the **GPT-6-Astra** baseline, this is a
gain of **31.11 score points** and **31.69 percentage points** in success rate.

**Leaderboard submission:** Our results are being submitted to the official RoboDojo leaderboard. The official results may vary slightly; we will update the results here once they are available.

| Method | Average score ↑ | Success rate ↑ |
| --- | ---: | ---: |
| SenseNova-RoboRSI / GPT-6 Astra (ours) | **60.08** | **54.17%** |
| EmbodiedEvo | 45.08 | 38.95% |
| VPP2 | 39.26 | 32.26% |
| PhysicalRSI | 36.27 | 31.38% |
| Awomo-0.5 | 35.34 | 29.64% |
| Simate-beta | 33.95 | 27.96% |
| GPT-6-Astra (baseline) | 28.97 | 22.48% |

Reference results: [RoboDojo simulation leaderboard](https://robodojo-benchmark.com/leaderboard)
(updated **2026-10-14**, accessed **2026-10-15**).

### [LIBERO-PRO](https://zxy-mllab.github.io/LIBERO-PRO-Webpage/)

| Method | Success rate ↑ |
| --- | ---: |
| SenseNova-RoboRSI / GPT-6 Astra (ours) | **94.50%** |
| RPent / GPT-6 Astra | 92.63% |
| RPent / Opus-4.7 | 82.40% |
| RPent / GPT-5.5 | 75.13% |
| RPent Flash Mode / Molmo2-8B | 72.63% |

The reference scores above, including GPT-6 Astra's 92.63%, are reported by [RPent](https://rpent.readthedocs.io/zh-cn/latest/rst_source/leaderboard/performance.html) on Task/Swap suites. The [official LIBERO-PRO leaderboard](https://github.com/Zxy-MLlab/LIBERO-PRO#-libero-pro-model-leaderboard) reports a different aggregate across five perturbation types.

### [RoboCasa365](https://robocasa.ai/)

| Method | Evaluation setting | Success rate ↑ |
| --- | --- | ---: |
| SenseNova-RoboRSI / GPT-6 Astra (ours) | Target kitchens + task memory | **64.60%** |
| Paimon-0 | Pretraining kitchens | 58.10% |
| Xiaomi-Robotics-1 | Pretraining kitchens | 57.40% |
| Phasor-m7 | Pretraining kitchens | 56.80% |
| ProWAM | Pretraining kitchens | 48.10% |

Reference results: [official RoboCasa leaderboard](https://robocasa.ai/leaderboard.html). SenseNova-RoboRSI uses the Target50 setting; the official entries use pretraining kitchens. These results provide context across different evaluation settings and do not establish a ranking under the same protocol.

## SenseNova-RoboRSI-27B-Preview

[🤗 The open-weight of SenseNova-RoboRSI-27B-Preview](https://huggingface.co/sensenova/sensenova-roborsi-27b-preview) is expected on **October 20, 2026**. A detailed **RoboRSI report** will follow the model release.

RoboRSI-27B-Preview turns validated interaction experience into reusable model
capabilities through joint model–Harness RSI. The open-weight release will support
community deployment, reproduction, and continued training.

![SenseNova-RoboRSI-27B-Preview results on RoboDojo, LIBERO-Pro, and RoboCasa365](assets/roborsi-27b-preview-benchmarks.webp)

- **RoboDojo:** Achieves an **average score of 26.13** and a **task success rate of
  20.83%** with VLA-assisted execution. Its average score is just **2.84 points**
  below GPT-6 Astra's score in the RoboDojo team's evaluation. The model actively
  inspects visual details, reasons about spatial relationships, and corrects
  actions based on execution feedback during complex manipulation tasks.
- **LIBERO-Pro:** Reaches **95.0% success** with VLA-assisted execution
  (System 2 + System 1) and **96.1%** with direct VLM control (System 2), ranking
  second to GPT-6 Astra among the compared models in both settings. These results
  demonstrate embodied planning and decision-making across different execution
  architectures.
- **RoboCasa365:** RSI training raises success from **26.0% to 46.5%** over the
  Qwen3.8-27B base model, while reducing average output tokens from **59.5K to
  15.9K**, a **73.3% reduction**. Learning from interaction experience improves
  both task performance and inference efficiency.

### Demonstrations

**Simulation · RoboDojo**

![Simulation · RoboDojo](assets/robodojo-27b-preview.webp)

**Real-robot demonstration**

![Real-robot demonstration](assets/real-robot-27b-preview.webp)

## Release Plan & Roadmap

### Release plan

- [x] Project introduction
- [x] [Empirical Study](https://www.sensenova.ai/has-gpt-6-astra-achieved-embodied-intelligence)
- [x] Initial code release: Agent runtime and LIBERO-family evaluation
- [x] [Usage documentation](docs/README.md)
- [ ] Harness demo
- [ ] SenseNova-RoboRSI-27B-Preview weights — expected October 20, 2026
- [ ] RoboRSI Technical Report

### Research roadmap

- **Experience retrieval.** We plan to organize successful strategies, failure
  cases, and execution traces into a searchable experience library.
- **Transfer across tasks and environments.** We will investigate whether tool
  combinations, planning strategies, and feedback mechanisms validated in one
  setting can provide useful starting points in another.
- **More robot platforms and real-world scenarios.** We aim to extend integration
  and evaluation to more robot embodiments and physical settings, and examine the
  reliability of feedback-driven improvement in those environments.
- **Joint model–Harness RSI.** Continue converting validated interaction
  experience into training supervision, retest model and system changes together,
  and measure capability and efficiency across improvement rounds.

## Community & Acknowledgements

We welcome collaboration with teams working on foundation models,
VLA policies, simulation platforms, and real robots.

- **Contributions:** We welcome new integrations, evaluation tasks,
  reproducible failure cases, and suggestions for Harness design. See the
  [contribution guide](CONTRIBUTING.md) for the current release scope and checks.
- **Questions & collaboration:** Open an
  [issue](https://github.com/OpenSenseNova/SenseNova-RoboRSI/issues)
  describing your platform, use case, and proposed contribution.
- **Release updates:** Watch the
  [SenseNova-RoboRSI repository](https://github.com/OpenSenseNova/SenseNova-RoboRSI).
- **Acknowledgements:** We thank
  [RoboDojo](https://robodojo-benchmark.com/),
  [LIBERO-PRO](https://zxy-mllab.github.io/LIBERO-PRO-Webpage/),
  [RoboCasa](https://robocasa.ai/),
  [RPent](https://rpent.readthedocs.io/zh-cn/latest/), and the broader open-source
  community supporting embodied-agent research.
- **Licenses:** External models, simulators, and datasets retain
  their respective licenses.

**This achievement reflects the joint team's continued exploration and close collaboration in embodied AI and agent systems. SenseNova-RoboRSI has been used in the published report [Has GPT-6 Achieved Embodied Intelligence?](https://www.sensenova.ai/has-gpt-6-astra-achieved-embodied-intelligence). We will continue to advance and validate these technologies.**
