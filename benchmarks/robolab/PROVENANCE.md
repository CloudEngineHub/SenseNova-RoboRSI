# Full-task 1x provenance

The reference is an existing completed experiment, audited independently of the
new standard RoboRSI Agent. There are 120 task names, ten run IDs per task,
1200 scored trials, 685 successes and 515 failures. The exact success fraction
is `685/1200 = 0.5708333333333333`; mean native score is
`0.6804972351963321`.

| Reference folder | Trials | Successes | `episode_results.jsonl` SHA-256 |
| --- | ---: | ---: | --- |
| `2026-09-30_14-43-30_harness` | 150 | 99 | `bf6e257472ee0f8b7711ebbab1d004afdc29e0bda5d0b2ac81b9609fa7b5e493` |
| `2026-09-30_14-44-09_harness` | 150 | 100 | `c2ab41b1efe7276146aa11dd5f808d880754f66b93998b8c066a0376d034dc21` |
| `2026-09-30_14-44-57_harness` | 150 | 65 | `781d6d53361e38e18cb0d2c544af0ce5468f57956274af6ba39fea4e724df1a8` |
| `2026-09-30_14-45-15_harness` | 150 | 51 | `ce4764c3b89d4a19a8ea08a3b30118edf5fbe24649bdd4f63e15ca7cd8fbe8d0` |
| `2026-10-01_05-50-49_harness` | 150 | 102 | `d03d87a1db2949b8e22ce589d1a3ccc25ff8142db07ffab61f979ec091e2258e` |
| `2026-10-01_05-51-20_harness` | 150 | 81 | `f5a73585e3abd9275860d6845b07e0b29b540c14e841addb362f06746bc84b23` |
| `2026-10-01_05-52-20_harness` | 150 | 95 | `404fb280ea8cb1b797be31cf00cad3ca4cbcd82f79abe998cdc1dcec331eaad5` |
| `2026-10-01_05-52-31_harness` | 150 | 92 | `fea087d40d22f178b9b3be2e1dc70f7287e30d01244228c09a01912491483ad8` |

`reproduce.py` checks completed run identities, finite scores and native
artifact consistency before recovery and full-cohort completion. Each score must equal the final value of
`data/demo_0/subtask/score` in its readable HDF5 recording. Log schema, task, run,
environment index and success must agree with the result row. The launcher does
not infer task success from a model message or process exit status.

## Recipe and reset cohorts

`full_task_1x.json` fixes the eight 15-task shards and original settings:
`gpt-6-astra`, effort `max`, images 320, timeout 1200 seconds, 30 retries,
default instructions, realtime renderer, all video, one environment and no
exploration. Native time budgets are 20–300 seconds at a control interval of
`8/120` seconds, or 300–4500 physical control frames. There is no 5x multiplier.

Each task starts a seed-zero environment. The original runner resets it twice
before each sequential run and invokes `reset_eval_state()` between runs.
Historical resumes restarted a seed-zero environment, then skipped previously
completed run IDs without advancing the RNG. Consequently run ID 7 is neither
seed 7 nor necessarily the seventh reset cohort of an uninterrupted run.

`historical_schedule.json` records all 24 completed worker processes in five
ordered process groups: `6xGh2JUd`, `rg6gSFC0`, `eMM0LY98`, `5uhQet6m`, and
`dauuNNtc`. Sixteen tasks span restart boundaries. The schedule retains exact
task/run segments, CLI versions and source-log hashes. Eighteen unscored,
interrupted attempts are excluded; they are not retries to count as failures or
extra scored trials. GPU concurrency can change without changing the order
inside each native process or the recorded phase barriers.

The 1200 CSV usage records were matched to their completed app-server event
streams using the full six-value token-usage tuple. This disambiguates the
cohorts from interrupted attempts instead of relying only on folder names or
the most recent source configuration.

## CLI versions

CLI `0.159.2` produced 1168 scored trials. CLI `0.160.0` produced these 32:

| Task | Run IDs |
| --- | --- |
| `PlasticBottlesInSquarePailTask` | 5–9 |
| `BlocksInBinTask` | 3–9 |
| `OneBottleOnShelfTask` | 0–9 |
| `PickDrillTask` | 0–9 |

The complete official package and native binary identities are in
`robots/robolab/agents/historical/codex-binaries.json`. Both versions are required
by the historical launcher. The standard Agent uses only 0.160.0 and a different
framework-owned `codex exec` / MCP protocol.

## Source and runtime limits

The source repository anchor is `7a06ccba58ea81bbe5c8fc91268f81f5243cbe80`;
its RoboLab gitlink is `92ccc0ee1984a272d4748c92ed73144fa806a6f4`. The current
checkout also contains later unrelated changes, so it was not copied wholesale.
The original executor, system/note prompts and WebSocket contract were checked
against the anchor. Source commits were not recorded per historical episode,
and an uncommitted runtime tree cannot be reconstructed conclusively from Git
alone. These values identify the migration's anchors, not an asserted exact
historical source lock.

The asset tree was checked against the pinned RoboLab revision: 1619 Git LFS
SHA-256 objects and 609 ordinary Git blobs, no missing or extra files. The
framework directory digest also includes paths and empty directories. Source
archives, 24-file Isaac Lab compatibility patch and native file hashes are
delivered in the build materials.

The image's simulator build and checked physics libraries match the historical
native installation, but the full Python/CUDA/Warp environments do not. The
image uses standalone Python 3.12.13/Torch CUDA 12.8; the historical host used
Python 3.12.14/Torch CUDA 13.0. The historical host had unresolved package
metadata conflicts; the new minimal native image has a separately resolved lock
and must pass its own `pip check`. Renderer materials referenced by upstream USD
assets can require public NVIDIA content URLs; disconnected rendering can fall
back to missing materials. Normal evaluation needs those resources available.

No new 1200-episode model run is claimed. Fixed-action native checks establish
transport, budgets, scoring and artifact behavior on the delivered route; they
do not establish model quality, all-task success or historical bitwise identity.
