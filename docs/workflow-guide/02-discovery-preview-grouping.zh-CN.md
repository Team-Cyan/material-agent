# 02 · 发现、预览与分组

## 发现与拍摄时间

[`io/scanner.py`](../../src/material_agent/io/scanner.py) 的 `scan_arw_files()` 递归列出配置 `raw_extensions` 中的扩展名并排序；名字虽叫 ARW scanner，能力不只 Sony ARW。目录不可读、缺失或不是目录时，由 command 前置检查拒绝。单次 run 的文件集合是后续分组依据；增量运行不会先把 `done` 文件滤掉。

[`domain/grouper.py`](../../src/material_agent/domain/grouper.py) 的 `read_exif_datetimes()` 优先从 processed DB 的 `exif_cache` 查找，再以最多 256 个文件一批调用 ExifTool 读取 `DateTimeOriginal`；批量失败或漏项会逐文件回退。能读到的原始字符串按 `%Y:%m:%d %H:%M:%S` 解析。缺 EXIF、格式异常或读取失败会得到未知时间；此类照片会成为独立边界，不会仅凭文件名猜测时刻。

Exif 与 pHash cache 均由源文件大小和纳秒 mtime 辅助识别变化。mtime/size 相同不等于内容密码学同一；分组 hash 另有 preprocessing 前缀 `phash-exif-v1:`，旧格式或未知版本缓存不会直接当有效值使用。

## RAW、embedded preview 与尺寸

[`domain/scoring_engine.py::decode_raw`](../../src/material_agent/domain/scoring_engine.py) 使用 rawpy 打开 RAW，先尝试 `extract_thumb()`：JPEG thumbnail 会解码并转为 RGB，bitmap thumbnail 也转成 RGB；若没有受支持的嵌入预览，再用 LibRaw `postprocess(use_camera_wb=True, output_bps=8, half_size=True)`。默认 `prefer_embedded: true`，因此常走相机生成的预览；它不代表 full-resolution RAW 解码或相机 RAW 全像素评分。

解码记录 `preview_source`、RAW 原始宽高 `original_size` 与缩放预览宽高 `preview_size`。focus 灰度图默认最长边上限 2048；用于 JPEG/模型输入的另一份预览默认最长边 1024、质量 85。RGB 在灰度分析后会于 OpenCV JPEG 编码前转换为 BGR，以保证编码后的颜色正常。分组 hash 输入也使用 EXIF display orientation 校正，再缩到 256 边以内计算 pHash。

全图 sharpness 仅承担灾难级模糊的快速保护；主体/眼睛焦点评估使用较大的 focus 灰度预览和检测 ROI，模型无可靠 ROI 时使用 saliency fallback。可选 selective refinement 可能关闭 embedded 优先并用 RAW half-size 获取更大 focus 观察；只有有效 focus 像素面积增长时才接受新结果。它不会因为来源是 RAW 就默认认为观察更好。

## 相邻 time AND pHash

当前 Grouper 先按时间排序，未知时间排在末尾；只比较排序序列中相邻照片，不构造全对全关系。两个相邻照片合并需同时满足：

1. 两者拍摄时间均已知，时间差不大于 `grouping.time_gap_seconds`；
2. 当 hash threshold 大于 0 时，两张图都有有效 pHash，且 Hamming distance 不高于 threshold。

因此它是时间与视觉相似度 **AND** 门槛。阈值 `0` 的语义是跳过 hash 判断，仅按相邻已知时间间隔合并；它不是“相似度必须为零”。任一相邻对断开后，后续照片只和新的前一张比较，所以连续 pair 可以形成链式组：A-B 与 B-C 都满足规则时 A/B/C 同组，即便 A-C 距离超过 threshold。缺 hash 会拆开而不是自动合并。

缓存只保存成功 hash，`visual_hash_cache` 以 path 为键，并记录文件指纹。运行时从有效前缀读取；缺项会重算。统计日志包含 reused/computed/missing hash、拆分原因和组跨度，用于解释分组结果，不改变规则。

### 已知合同限制

曝光包围照片如果在时间窗口内但 pHash 超过阈值，会被拆成单张；随后组 coverage 可能保留低质量 singleton。review 的公开 CR2 例子中暗帧 distance 为 24/64、threshold 为 10，最终作为 coverage 被保留。针对该例的 equalized/autocontrast pHash 和 dHash 比较已完成，且后续比较发现误合并/失败候选；当前限制不是新回归，也没有被阈值拟合解决。只有新独立数据和新归因假设才会重开。

## 所有权线索

- 扫描：[`io/scanner.py`](../../src/material_agent/io/scanner.py)；[`commands/scoring.py`](../../src/material_agent/commands/scoring.py)
- EXIF、hash 与分组：[`domain/grouper.py`](../../src/material_agent/domain/grouper.py)
- RAW 预览解码：[`domain/scoring_engine.py`](../../src/material_agent/domain/scoring_engine.py)
- 聚焦 ROI：[`domain/subject_focus.py`](../../src/material_agent/domain/subject_focus.py)；[`domain/evidence_refinement.py`](../../src/material_agent/domain/evidence_refinement.py)
- 核心回归：[`tests/test_grouper.py`](../../tests/test_grouper.py)、[`tests/test_preview_decode.py`](../../tests/test_preview_decode.py)、[`tests/test_subject_focus.py`](../../tests/test_subject_focus.py)
- 正式契约：[grouping](../ai/modules/grouping.md)、[scoring engine](../ai/modules/scoring-engine.md)
