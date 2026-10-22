# 03 · 评分、选择与解释字段

## 单张照片的计算顺序

`compute_scores()` 位于 [`domain/scoring_engine.py`](../../src/material_agent/domain/scoring_engine.py)，输入是受限 RAW 预览 `RawFrame`、local client、规范化配置与可选 screening port。大体顺序如下：

1. 从灰度预览计算启用的 exposure、全图 sharpness 等 CPU 技术指标，生成局部指标和曝光/模糊证据。
2. 如果 `focus_integrity.mode: subject_roi` 且全图锐度低于 `global_blur_reject_below`，提前返回 catastrophic blur rejected；不会把这种 rejection 伪装为完整 learned inference。
3. 当 screening 启用时，pixel tier-1 低于阈值可提前返回；再可调用 fast screening，tier-2 低于阈值时提前返回。screening 异常记录为 `fast_error` 并继续，不自动当作拒绝。当前默认 screening 关闭。
4. 对启用的 vision 维度调用 `client.score_image()`。默认 `local` client 使用本地启发式视觉信号/场景，不需要网络服务。随后按识别场景重算 exposure，并在检测结果基础上测量 subject/eye ROI focus；无可靠检测时使用 deterministic saliency fallback。
5. 整理分数、scene、模型元数据和 layered signals，交给 `summarize_signals()` 产生唯一权威 `total`、质量决策和可见 breakdown。正常与 early rejection 共用这套 layered 汇总，而不是另有像素分与视觉分直接平均的旁路。

源码链接：[compute_scores](../../src/material_agent/domain/scoring_engine.py)、[LocalBackendClient](../../src/material_agent/clients/local.py)、[subject focus](../../src/material_agent/domain/subject_focus.py)、[layered decision](../../src/material_agent/domain/layered_decision.py)。

## 默认、可选与实验性信号

仓库默认配置中 exposure、sharpness 和 subject/composition/lighting/color/clarity/depth/mood 维度启用；Local heuristic 路径正常运行。以下 block 默认关闭或受额外配置约束：

| 层 | 当前用途 | 仓库默认 |
| --- | --- | --- |
| MUSIQ fast screening | 两级快速 screening，可能提前筛除 | `screening.enabled: false` |
| OpenCLIP MobileCLIP2 semantic | 可选语义相似/分类信号 | `local.semantic.enabled: false` |
| BRISQUE / NIQE | `reject_prior` 原始质量先验，不直接当总分 | `local.quality.enabled: false` |
| MUSIQ / PyIQA quality | quality model block；需校准与显式启用 | 关闭 |
| NIMA OpenVINO aesthetic | `overall_aesthetic` learned aesthetic signal，可配置 calibration | `local.aesthetic.enabled: false` |
| SSD MobileNet 检测 | subject/object ROI 辅助 | detection adapter 依配置启用；无可用权重时显式 fallback |
| YuNet face/eye localization | ROI/眼部证据；不等于好坏人脸判断 | `local.face.enabled: false` |
| DINOv2 embedding | 局部向量/相似分析能力，不是默认评分融合项 | `local.embedding.enabled: false` |
| MediaPipe face structure | 可选面部结构分析 | `local.face.enabled: false` 时不加载 |
| selective refinement | 小组中有限扩大 focus 观察 | `focus_integrity.selective_refinement.enabled: false` |
| portrait face-eye policy | 把适用眼部证据纳入 policy | `portrait_face_eye.enabled: false` |

local optional modules 按启用状态 lazy import；缺依赖/权重通常返回 fallback metadata，`enforce_available: true` 时则显式失败。当前配置和 adapter 能力比“仓库里有这个模型文件”更能说明一次任务是否用到模型。MUSIQ screening 与 quality role 是不同入口；BRISQUE/NIQE reject prior、quality score、aesthetic score不可互换。

需把 profile 区分开：仓库根目录 `config.yaml` 默认将 NIMA、semantic、quality、embedding、face、screening 和 selective refinement 关闭；发布的 Intel 镜像使用 [`docker/config.intel-openvino.yaml`](../../docker/config.intel-openvino.yaml)，其中 NIMA aesthetic、SSD detection 与 portrait face/eye policy 显式启用，模型请求 CPU 并强制可用。镜像 profile 不是所有运行的默认配置，也不证明目标硬件上发生了加速。

## `quality_assessment`、`selection` 与其他字段

| 字段/阶段 | 表达的事实 | 不保证什么 |
| --- | --- | --- |
| `score_total` 与各 `scores` | 当前评分策略按场景/信号融合的连续分数 | 不是真实用户偏好或绝对质量真值 |
| XMP `rating` / `star_rating` | 总分映射为 0–5 星（每 2 分约 1 星、四舍五入并夹在范围） | 有既存非零用户 rating 时不会覆盖；也不是相机软件内的独立评级 |
| `meta.quality_assessment` | 保留原始逐张质量 decision 与缺陷 reasons | 不包含“这个组必须留一张”的覆盖策略 |
| `meta.selection` | 组内保留角色、选择 decision 与选择原因 | keep 不代表其单张质量突然变好 |
| `decision` | 兼容字段，当前代表 selection 结果 | 旧调用者不能把它当纯 quality verdict |
| `group_coverage` / `group_coverage_fallback` | 当启用分组与 best-candidate review 时，若可评分照片中 quality policy 没有 keep，选最高有限分作为显式候选 | 不修复分组错误，也不证明保留图满足质量标准 |
| `group_rank` / `rank` | 当前组中按有效分数排序的位置，稳定 tie 规则由 job 实现 | 增删成员可能改变 rank；不是全库名次 |
| `group_commentary` | 可选语言模型/本地 client 生成的组级文字摘要 | 不是结构化决策本身，也不取代质量/选择字段 |
| finalization | refinement → commentary → coverage selection；后写 rank/metadata | 不保证 refinement 提升质量；异常/预算耗尽可保留 baseline 并记录需 review |

`apply_group_best_candidate_review()` 以 versioned `quality_assessment` 为基线，再独立计算 selection；refinalize 不会把先前 coverage fallback 当成质量 keep。coverage 排除 decode error、未评分 payload。分数和 stars 不因 coverage 改变。

### 排序、commentary 与写出

`ReviewPhotosJob` 在每组内先读缓存或算分，必要时对少数 close candidates 做 refinement，然后组级 commentary，之后 domain selection，最后按排序给 rank 并调用 writer。`ReviewRunService`/`review_runtime.py` 把 orchestration 与 domain policy 分开。commentary 默认关闭；启用后也不改变原始单张质量字段。若组里全是可跳过的 done cache，job 可以直接跳过终端 writer——当前 Web dry-run 的这条缓存分支会造成预览缺项（见 01、07）。

## 人工标签和评估边界

分数、星级、coverage 和组排名都是产品策略字段；要声称对真实用户选片有帮助，仍需适当的人类参考集。G1/G2 是条件性科学门槛；MOS、动作标签、文件名和 synthetic 组件指标不能代替该目标。相关评估脚本和完成/未完成状态集中在 [章节 08](08-operations-source-index.zh-CN.md) 与 [roadmap](../roadmap.md)。

## 关键契约与测试

- [评分引擎契约](../ai/modules/scoring-engine.md)
- [`domain/scoring_engine.py`](../../src/material_agent/domain/scoring_engine.py)、[`domain/layered_decision.py`](../../src/material_agent/domain/layered_decision.py)、[`app/review_runtime.py`](../../src/material_agent/app/review_runtime.py)、[`app/jobs/review_photos.py`](../../src/material_agent/app/jobs/review_photos.py)
- [`tests/test_scorers.py`](../../tests/test_scorers.py)、[`tests/test_review_finalization.py`](../../tests/test_review_finalization.py)、[`tests/test_review_job.py`](../../tests/test_review_job.py)、[`tests/test_evidence_refinement.py`](../../tests/test_evidence_refinement.py)
