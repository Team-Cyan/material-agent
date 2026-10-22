# 05 · SQLite、缓存与恢复

## 两个 repository 的分工

当前通常是一个 `state.db` 文件，但由 runtime 与 processed 两个 repository/SQLite connection 管不同记录。Web library index 也使用 runtime DB 的扩展表。

| Repository | 核心表/概念 | 谁读写、解决什么问题 |
| --- | --- | --- |
| [`SQLiteRuntimeRepository`](../../src/material_agent/adapters/state/sqlite_runtime.py) | `sessions`, `jobs`, `job_files`, `artifacts`, `events` | 每次运行的生命周期、逐文件结果、可重启检查的 score payload、事件与 Web 查询 |
| [`SQLiteProcessedRepository`](../../src/material_agent/adapters/state/processed_sqlite.py) | `processed`, `exif_cache`, `visual_hash_cache`, `embedding_cache`, `score_signals`, `xmp_projection_ledger` | 跨运行评分缓存与 `done` 状态、EXIF/hash/embedding cache、规范化 signals、XMP 投影 receipt |
| Web 索引 | `library_index`（runtime DB） | 只读照片库路径、大小、mtime 与 scan generation，供列表与详情查询 |

关系上，session 包含一组 jobs；每个 job 有多条 job_files；artifact 可挂在 job 或 job_file 上，`score_payload` 保存结构化评分，events 用于过程可观察。processed 是按 `file_path` 唯一的跨运行视图，不是每次运行历史的替代品；ledger 可保存一张照片多个 XMP 操作 receipt。

SQLite 使用 WAL 与 busy timeout，DB 文件权限由 helper 收紧。runtime 与 processed 使用独立连接访问同一 DB 文件，因此 runtime 的批量写入会在跨到 Grouper/processed cache 写操作前显式 `flush_pending_writes()` 释放 writer lock。

## 状态与取消

Session 状态包括 open/running/terminal；job 还记录 stage（discover/group/score/comment/write/finalize 等）与 queued/running/terminal 状态。job_file 状态区分 `scored`, `written`, `simulated`, `skipped`, `error` 等事实：

- `written`：job-file 以已写出状态保存；当前写出模式的 unchanged `done` cache shortcut 也会沿用/记录 `written`，所以需结合事件 `reason` 和 processed 记录判断本轮是否实际调用 writer；
- `simulated`：dry-run 终端结果已记录，但不表示源 sidecar 写出；
- `skipped`：例如 Web dry-run 中已处理文件被略过，不应描述成当前轮又写了一次；
- `error`：该文件本轮未完成预期操作；批次可成为 `finished_with_errors`。

Job/session 终态包括 `finished`, `finished_with_errors`, `failed`, `cancelled`。SIGTERM 由 `sigterm_as_cancellation` 和 CLI 捕获转换为取消，CLI 返回 130。成功完成一部分文件后取消，已提交批次会保留，当前未提交批次可以 rollback。启动新 run 前 `reconcile_abandoned_runs()` 会将上次留下的 open/running 等非终结 session/job 以 `abandoned_before_current_run` 归为 cancelled。

这叫有限的 abandoned record reconciliation，不是自动从同一个 job 精确续跑，更不是整个 appdata 恢复。恢复依赖 processed rows 和 runtime artifacts 创建后续运行复用。whole production-appdata restore、原子 DB/XMP crash consistency、same-job resume 尚未获得保证。

### 提交粒度

runtime repo 可通过 `batched_commits(commit_every=2048)` 合并大量逻辑 commit；batch 正常离开时提交，异常时回滚当前 batch。job 结果和输出 artifact 仍按 bounded 单元写入。取消或进程崩溃可能留下之前已提交的完整文件和未完成运行记录；下一次 startup reconciliation 解释旧 run，incremental pipeline 再判断哪些文件可复用。

## 文件与评分缓存身份

processed `processed` 行保存 status、score、scene、decision/reasons、group metadata、commentary、score metadata、file size/mtime、cache key 与序列化 `xmp_payload`。缓存评分时至少比较文件指纹和 `score_cache_key`。score key 包含 pipeline revision、相关规范化配置（包括 scorer、scene、grouping、preview、focus、commentary、XMP 等）、运行时发行版本、启用模型的资产 digest；特定 quality/embedding block 启用时还包含其证据/identity revision。

EXIF/hash/embedding cache 分别保存自己的输入/模型 identity。embedding 向量只作 transient/cache 输入；写入普通 score metadata 时会剔除 raw vector 字段。读取历史行时，以兼容为目的允许某些 fingerprint 尚为空的旧行，直到下次成功写入才补齐；因此“legacy row readable”与“新写入严格记指纹”并存。

`reprocess` 强制对目标集合走重处理；mutating run 和维护命令共享一个 work-dir lock。它不会取消 XMP writer 的并发修改保护，也不意味着所有历史数据都被抹除。清状态和清 sidecar 是单独命令与不同副作用。

## 两套状态与 Web dry-run 的差异

Web dry-run 会建立 runtime session/job/job_file/event/artifact，以便 dashboard 观察，但不应创建 processed 新评分、`done` 或 source XMP。CLI 写出模式完成后才将终端 score 与 XMP payload 投影存入 processed。已有 done processed cache 可在 Web 查询/score 时作为读取来源，但 dry-run 本身不更新 processed 行。

当前匹配 `done` cache 的 Web dry-run 若组信息不变，可由 `ReviewPhotosJob` 跳过 writer；由于 `output_preview` 目前是在 write callback 中添加，artifact 可能没有预览。这是 review 确认的 R3 缺陷，计划要求仅重新构建 DB-only preview，不重算、不碰 sidecar；尚未修复。

## 源码与测试

- [runtime-state 契约](../ai/modules/runtime-state.md)、[review pipeline 契约](../ai/modules/review-pipeline.md)
- [`sqlite_runtime.py`](../../src/material_agent/adapters/state/sqlite_runtime.py)、[`processed_sqlite.py`](../../src/material_agent/adapters/state/processed_sqlite.py)、[`app/jobs/review_photos.py`](../../src/material_agent/app/jobs/review_photos.py)
- [`tests/test_runtime_state.py`](../../tests/test_runtime_state.py)、[`tests/test_state.py`](../../tests/test_state.py)、[`tests/test_review_job.py`](../../tests/test_review_job.py)、[`tests/test_run_control.py`](../../tests/test_run_control.py)
