# R08–R10 跨机器续跑：归档与迁移状态

核查时间：2026-09-08。已封存的 R01–R07 产物可以从 GitHub 恢复。
Git 仓库、Release 数据包和目标源码仓库共同组成迁移输入；模型权重及
DCU/DTK 运行环境需要在目标机器另行准备。

**当前尚不能在干净 checkout 上直接执行 `--resume-from R08`。**
已归档的状态仍是 `R07=stopped`、`R08–R10=pending`，已完成的离线恢复
记录为 `R07.recovered.json`，其状态是 `complete_recovered_offline`。
原调度器要求正式的 `R07.json` 和完整的 scheduler ledger，尚未接入该恢复
状态。迁移时需要显式接入恢复证据，并保持其来源和完成边界。

## 本次补齐的内容

新增 [迁移输入 Release](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r08-continuation-inputs-20260908)：

`r08-continuation-sources-inputs-control-20260908.tar.gz`

压缩包约 20.54 MB，包含 92 个文件：

- 旧容器实际使用的 scripts、configs、manifests、skills 和 workflow 源文件；
- R01–R06 恢复索引、handoff、阶段产物清单和重建记录；
- 固定输入 `16-32K_throughput.jsonl`，SHA-256 为
  `633ba4c8b4f500d2ab28094de42698c5494e5232f40eafcd119c0a314b44b936`；
- 模型配置、权重分片文件名/大小清单，以及采集器 Python 环境的包版本；
- 原 HIPProf 的路径与 SHA-256 身份，未打包二进制或模型权重。

旧容器实际调度器为 830,769 字节，SHA-256：
`f639692bdbb7a7f248b5f610a3ba854b5bdac30a6865211e3b1879c1d89a2fd4`。
Git 当前主路径中的版本为 96,680 字节，SHA-256：
`73f2a85b0a28510867774775fc01568f2cf8870740153de9a50fb475b72b229b`。
实际运行版本保存为独立快照，未覆盖主路径中的代码。部署时需要一起核对
配套配置、技能、manifest 和调度器，不能任意混用版本。

快照已完整解压读取，逐文件核验 SHA-256；清单在 `SNAPSHOT_MANIFEST.json`。
本次读取没有运行模型或查询 DCU。

## 其他必需归档

所有下载地址、大小和服务器 SHA-256 见 `RELEASE_CATALOG.json`。部分旧包内
README 保留历史仓库名称，优先使用该目录中的 `cspool/auto_trace` 下载地址。

| 内容 | 远程位置 | 解包位置 |
|---|---|---|
| 工作流主仓库 | https://github.com/cspool/auto_trace | 项目根目录 |
| 固定目标源码 | https://github.com/cspool/dcu-home/tree/repro-gqa-page784-k5120-batch8-final | 项目根目录下 `pra2026-bh408-gqa-page784-k5120-batch8` |
| R01–R03 | [Release](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r01-r03-batch8-dp2-fresh-003-20260827) | 下述 run 目录 |
| R04–R06 | [Release](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r04-r06-batch8-dp2-fresh-003-20260829) | 下述 run 目录 |
| Attempt 43 已恢复的 R07 消费包 | [Release](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-attempt043-offline-recovery-20260907) | 项目根目录 |
| R07 完整取证补充数据 | [Release](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r07-local-artifacts-20260907) | 使用对应目录的 `restore.py` |

固定目标源码 commit：`2b4b2119ae3cc2c4c626dc5690ef9593c1477f66`。

run 目录相对项目根目录为：

```text
perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003
```

R01–R03 和 R04–R06 的归档成员以 `artifacts/`、`handoffs/` 开头；因此应解压
到 run 目录。R07 消费包的成员以 `perf_trace_batch8/` 开头，应解压到项目根目录。
全部归档都应先核对分片/压缩流校验和，再解包。

用于继续分析时，优先恢复约 154 MB 的 R07 消费包。完整 R07 取证恢复会重建
约 128.8 GB 的逻辑文件，还需要下载缓存空间；它不能代替单独恢复 R01–R06。

## 在新机器拉取本次快照

以下命令只下载和检查资料，不会启动调度器或采集任务：

```bash
git clone https://github.com/cspool/auto_trace.git
cd auto_trace

mkdir -p ../auto_trace-migration-20260908/snapshot
cd ../auto_trace-migration-20260908
curl -fL --retry 3 -O https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-r08-continuation-inputs-20260908/r08-continuation-sources-inputs-control-20260908.tar.gz
curl -fL --retry 3 -O https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-r08-continuation-inputs-20260908/SNAPSHOT_ARCHIVE_SHA256
sha256sum -c SNAPSHOT_ARCHIVE_SHA256
tar -xzf r08-continuation-sources-inputs-control-20260908.tar.gz -C snapshot
cd snapshot
sha256sum -c SNAPSHOT_FILES_SHA256SUMS
```

## 启动 R08 前仍需完成

1. 在目标环境准备两张适配当前 gfx936/DP2 合同的 DCU、匹配的 DTK/HIPProf、
   Python/vLLM ABI 和 Qwen3.5-27B 权重。核对模型配置及原始输入哈希。
2. 恢复 R01–R06 和 R07 消费包，按各自 handoff 核验所有依赖文件。
3. 重建逻辑路径及必要软链接。现有配置含
   `/public/home/tangyu408/Qwen_DCU_Worker_0`、`/home/testdata`、
   `/perf_trace_batch8_r01_r06` 等绝对路径；跨账户或跨机器不能仅复制目录名。
   原始元数据保留原字节，路径重绑定应另有可审计记录。
4. 实现并验证 recovery-aware 的 R07→R08 接入，接纳
   `complete_recovered_offline`，保留“原始 HIPProf 生命周期未自然完成”的
   事实。不能仅改名为 `R07.json` 或修改 `status` 来绕过门禁。
5. R08 完成新采集、校验和归档后，R09/R10 可以在 CPU 机器进行。

已发布的旧 R08–R10 降级结果来自较早的 R07 部分覆盖数据，应保留其来源，
不能直接作为 Attempt 43 完整后续阶段的验收结果。

2026-09-08 的旧容器检查仍见原 HIPProf 进程存在，未发现新的正式 R07–R10
handoff。归档是已封存文件的快照，不包含运行中的进程内存、打开的临时文件
或未来才生成的结果。
