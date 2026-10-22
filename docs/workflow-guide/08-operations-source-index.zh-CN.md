# 08 · 维护命令、容器与源码索引

## CLI 命令按用途

真实参数以 `material-agent --help` 和 [`shells/cli/main.py`](../../src/material_agent/shells/cli/main.py) 为准。

| 命令 | 用途与边界 |
| --- | --- |
| `run` | 主产品扫描/分组/评分/投影；默认写出，`--dry-run` 仍创建 runtime job state |
| `web` | operator dashboard；Web 子任务固定 dry-run |
| `rescore` | 从 processed 中已有维度/证据重算 policy 决策；可按 scene 限定，不解 RAW、不写照片元数据 |
| `rewrite-xmp` | 从数据库重新投影机器管理的 XMP 字段；支持 dry-run；正常执行会触碰 sidecar，需审阅 ownership 和外部修改保护 |
| `rewrite-commentary` | 从既有 score 重新生成 commentary；只有显式 `--rewrite-xmp` 才同步写描述 sidecar |
| `reset-ai` | 清 AI 评分/评论状态；默认 dry-run，`--clear-xmp` 才清机器管理 XMP 字段 |
| `scan-scenes`, `suggest-scenes`, `remap-scenes` | 浏览/建议/更新 scene 映射字段；不是重新推理或 XMP 写出 |
| `review-scores` | 对保存的 score/job 做有界审阅报告；支持 job 固定比较，按参数选择是否重建预览，不是生产重评分 |
| `fix-db` | 修复 SQLite 数据质量；属于 mutating maintenance 命令，使用运行控制边界 |
| `models list/install/select/delete/serve` | managed model registry 或显式本地 model serving 操作；不是默认 run 的前置服务 |
| `benchmark-local` | manifest 驱动的隔离评估，只写指定 report，不建立生产 runtime/processed repository，也不写 XMP |
| `prepare-openvino-model`, `fit-aesthetic-calibration`, `benchmark-nima-device`, aesthetic labels | 模型资源准备、人工标签校准或设备诊断；需单独看命令作用目录与成本 |

所谓 dry-run 不是绝对无副作用：`run --dry-run` 会写 runtime DB、job/artifact/event 等；Web dry-run 还写日志、task state、配置快照、索引/缩略图。要完全限定写集，须读各命令 owner 与 repository contract。

## Benchmark 与生产路径

`benchmark-local` 使用独立 `material-agent.local-benchmark.v1` manifest，能比较固定 fixture、重复分数、scene/group metrics 和 runtime provenance；明确禁止构造生产 runtime repository、processed repository 或 writer。其他 `scripts/benchmark_*` 有各自的协议、数据集、摘要身份和接受范围。历史实验的性能数字、失败实验或 synthetic parity 不能直接当生产默认变更，也不能互相替代 G1/G2 人类标签。

项目进度文档记录 A1–A4 已结束：A1 legacy grouping/quality contracts；A2 preparation memory observations；A3 runtime responsibilities cleanup；A4 评估脚本维护审计。它们不等于产品质量改进或完整覆盖。G1 当前没有足够独立 directed reference pairs/families，G2 依赖 G1；因此相关重要内容覆盖仍属条件性科学验证。

有限 native quality、20 DNG RAW pipeline、恢复和 Bridge 证据已按各自固定 cohort 完成。报告保留过往失败与限制。该阶段不证明普遍 full-RAW 质量、Capture One/所有软件往返、JPEG embedded XMP 写入、vendor ID 全保留、atomic DB/XMP crash consistency 或 whole production appdata restore。G1/G2 和广泛格式兼容不阻碍本指南完成。

## Docker / CI / 外部部署

仓库提供 CPU 基础镜像与 Intel/OpenVINO 变体、入口脚本和 compose/容器契约；容器入口协调配置、read-only photo mount、writeable appdata、命令参数与 work directory。镜像构建/发布由 GitHub Actions 管理。CI 成功或 image publication 成功表示相应源码和构建检查通过，不代表私人 operator 已部署，也不代表某台主机的 runtime device 或照片验收通过。

公共仓库只记录通用 deployment contract，不写私人 NAS 地址、个人绝对路径、凭据或具体家庭网络信息。真实服务变更由外部 operator 工作流授权；本文档任务不运行真实照片任务、不下载模型、不写 XMP、不部署。

## 模块索引：从行为找到 owner

下表按职责而不是逐文件枚举。源码路径相对仓库根；测试是主要定位点，不声称覆盖所有组合。

| 责任 | 输入 → 输出 / 重要字段 | 上下游与 owning source | 契约 / 测试 |
| --- | --- | --- | --- |
| CLI 与配置 | argv + YAML → normalized config / validated args；`backend`, `raw_extensions`, `input_dir`, `reprocess` | `shells/cli/main.py` → `commands/scoring.py` → app | [`review-pipeline`](../ai/modules/review-pipeline.md), `tests/test_main.py`, `test_config_validator.py` |
| discovery/RAW/group | file paths → `RawFrame`, group members/IDs、EXIF/hash cache | `io/scanner.py`, `domain/grouper.py`, `domain/scoring_engine.py` → processed cache | [`grouping`](../ai/modules/grouping.md), `tests/test_grouper.py`, `test_preview_decode.py` |
| 单图评分 | preview + local client → `ScoreBundle`, `scores`, `signals`, `scene`, quality decision | `domain/scoring_engine.py`, `layered_decision.py`, `clients/local.py` → review job | [`scoring-engine`](../ai/modules/scoring-engine.md), `tests/test_scorers.py`, `test_review_finalization.py` |
| 任务编排 | job inputs + repositories → job_file/artifact/event 与 finalized results | `app/review_service.py`, `app/review_runtime.py`, `app/jobs/review_photos.py`, `app/job_executor.py` | [`review-pipeline`](../ai/modules/review-pipeline.md), `tests/test_review_job.py`, `test_app_services.py` |
| inference adapters | JPEG/model asset/config → signals + requested/compiled/execution provenance | `clients/local.py`, `adapters/models/*`, `ports/model_ports.py` | [`local-model-stack`](../ai/modules/local-model-stack.md), `tests/test_inference_lifecycle.py`, model adapter tests |
| SQLite state | session/job mutations + processed payload → WAL state/cache/receipts | `adapters/state/sqlite_runtime.py`, `processed_sqlite.py`, `ports/state_ports.py` | [`runtime-state`](../ai/modules/runtime-state.md), `tests/test_runtime_state.py`, `test_state.py` |
| XMP writer | score/group/commentary → preview receipt or sidecar projection; rating/keywords/instructions/description | `adapters/metadata/exiftool_xmp.py` ← `app/review_runtime.py`, rewrite service | [`xmp-writer`](../ai/modules/xmp-writer.md), `tests/test_writer.py`, `test_xmp_projection_ledger.py` |
| Web operator plane | REST request → config/task/index/model operation; dry-run artifact；私有双租约/回执用于重启与取消 | `app/web_service.py`, [`app/web_worker.py`](../../src/material_agent/app/web_worker.py), `app/model_catalog_service.py`, `web/app.js` | [`web-operations`](../ai/modules/web-operations.md), `tests/test_web_service.py`, `test_model_catalog_service.py` |
| isolated evaluation | manifest/protocol + bounded fixtures → report JSON/Markdown | `app/local_benchmark_service.py`, `commands/benchmark.py`, `scripts/benchmark_*` | [`local-benchmark`](../ai/modules/local-benchmark.md), `tests/test_local_benchmark.py` |

`core/pipeline.py`, `core/grouper.py`, `core/scoring_engine.py` 与顶层 `main.py` 保留历史 API/import compatibility。旧 provider 目录 `clients/ollama.py`, `clients/omlx.py`, `adapters/models/{ollama,omlx}` 也保留显式兼容/实验用途。默认业务实现不应被误认为这些 wrapper/legacy 代码的平行版本；新改动先看 domain/app/adapters 的 owning module。

## 术语表

- **preview**：供评分或缩略图消费的有界图像，不等于完整 RAW 像素。
- **pHash distance**：感知哈希 bit distance；越小通常越相近，受 preview 和方向处理影响。
- **processed cache**：跨运行按文件保存的 score/projection 状态。
- **runtime artifact**：某个 job/job-file 保存的完整结果快照，便于 Web 展示或恢复。
- **projection / receipt**：计划将字段写到 XMP 或记录实际写入结果的结构化数据。
- **quality assessment**：每张照片原始质量政策结果。
- **selection / coverage**：为组内保留代表照片而叠加的选择结果。
- **CPU fallback**：请求设备不可用或适配条件失败时退回可用 CPU 路径；不是成功使用加速器。
- **dry-run**：不执行指定对象写出（如 XMP），但仍可能写 appdata、DB、日志和报告。

## 建议逐章 review 的问题

1. 组 coverage 是否应该在没有明确质量 keep 时保留最高分代表，还是应把“质量拒绝”与“目录覆盖”分成不同可操作的产品状态？
2. 以 `DateTimeOriginal` 与相邻 AND pHash 为默认分组，是否足够贴近连拍和曝光包围习惯？若要改，需要怎样的新独立正/反例证据来避免按单个失败片段调阈值？
3. 哪些 optional signals 值得进入默认评分？需要何种独立人工标签、资源约束和可解释字段，而不仅是模型可运行？
4. `processed` 的 path + size/mtime + cache identity 对长期归档是否足够？用户期望发现原文件被同尺寸同 mtime 替换时如何处理？
5. XMP 与 SQLite 不可共同原子提交时，用户需要什么 reconciliation UI/命令，如何避免重复写入或覆盖外部修改？
6. Web 如果仅适合 trusted LAN，部署方需要何种网络隔离/认证边界？R1 worker 状态、R2 model lease、R3 preview 和 R4 receipt 的修复验收是否符合 operator 预期？
7. 哪些 Bridge/native/recovery 证据足以支撑目标格式；Capture One、JPEG embedded、DNG 与 broad vendor metadata 的优先级是什么？
8. G1/G2 若长期缺合格独立判断，产品应保持现状、简化目标还是改变验证计划？MOS、benchmark 分数不应在未决定目标前替代它。

## 文档与验收来源

- [项目总览](../ai/project-overview.md)、[模块目录](../ai/modules/README.md)、[当前 roadmap/status](../roadmap.md)、[2026-10-22 review](../operations/2026-10-22-repository-review.md)、[follow-up plan](../operations/2026-10-22-follow-up-plan.md)
- [A1–A4 状态与条件门槛](../operations/2026-09-16-plan-status.md)
