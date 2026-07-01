# OMLX Benchmark Matrix

这份文档是写给“不想自己翻 `artifacts/benchmarks/*.json`，但想快速知道这些 benchmark 当时在测什么、结论是什么”的人看的。

## 一句话理解

仓库里的 `artifacts/benchmarks/` 目前只保存了 **OMLX 请求层 benchmark**，不包含真实样片 harness。

所以这份矩阵主要回答：

- 哪个模型能不能稳定返回 JSON / schema
- 单图大概多快
- KV cache batch 大概多快
- 当时扫出来的最佳请求参数组合是什么

它**不直接回答**：

- 真实照片点评质量谁更好
- 后期建议会不会模板化
- 场景描述会不会 hallucinate

这些要看 `omlx-harness` 和 `/tmp/...` 里的 live harness 报告。

## 先看这 3 类文件

每组 benchmark 基本都有这 3 类文件：

- `best_candidates.json`
  - 结论版
  - 只保留每个模型在这一组实验里的最佳候选参数
- `<timestamp>/summary.json`
  - 汇总版
  - 包含本次 run 的模式、样本、preflight、完整结果列表
- `<timestamp>/attempts.jsonl`
  - 明细版
  - 一行一个 attempt，适合追查 507、schema 失败、单次延迟抖动

## 环境说明

这批 benchmark 共同特征：

- OMLX runtime：`0.3.4`
- `structured_outputs_available=false`
- `xgrammar_available=false`
- 实际 constraint path：
  `response_format_json_schema -> prompt_injection_and_post_parse`

也就是说：

- 这些结果是基于当前 DMG 桌面版 runtime 的现实行为得到的
- 不是基于更严格的 `structured_outputs/xgrammar` 路径

## Benchmark Matrix

| 目录 | 主要用途 | 最佳候选 | 你该怎么理解 |
|---|---|---|---|
| `omlx-five-models-smoke` | 五模型快速 smoke，先看谁能基本跑通 | `Qwen3-VL-4B`, `qwen3`, `1024`, `jpeg 92`, `4326.51 ms`, `100% json/schema` | 这是“快速体检”，不是最终排序。 |
| `omlx-five-models-single` | 五模型单图混跑对比 | `Qwen3-VL-4B` `2109.6 ms`、`gemma-e2b` `1273.71 ms` 成功；其余候选这里有失败 | 混跑时资源和装载冲突更明显，只适合先筛候选，不适合下最终结论。 |
| `omlx-single-isolated-qwen8` | 单独验证 `Qwen3-VL-8B` 的单图请求 | `qwen3`, `1024`, `jpeg 92`, `7373.09 ms`, `100% json/schema` | `Qwen8` 不是不能跑，只是明显偏慢。 |
| `omlx-single-isolated-gemma-e4b-4bit` | 单独验证 `gemma-e4b-4bit` 单图请求 | `gemma`, `1024`, `jpeg 92`, `3095.94 ms`, `100% json/schema` | `e4b-4bit` 隔离后能跑，但后续是否值得默认还要看 harness。 |
| `omlx-single-isolated-gemma-e4b-8bit` | 单独验证 `gemma-e4b-8bit` 是否能活着跑起来 | `768`, `jpeg 92`，但 `0% json/schema`，典型错误是 `507 Insufficient Storage` | 当前机器上基本不可作为常规候选。 |
| `omlx-kv-isolated-qwen4` | `Qwen3-VL-4B` 批量 KV cache 测试 | 首张 `7951.64 ms`，后续 `7206.65 ms`，均值 `7299.78 ms` | 稳，但不快。 |
| `omlx-kv-isolated-qwen8` | `Qwen3-VL-8B` 批量 KV cache 测试 | 首张 `14015.34 ms`，后续 `12381.18 ms`，均值 `12585.45 ms` | 太慢，不适合默认主路径。 |
| `omlx-kv-isolated-gemma-e2b` | `gemma-e2b` 批量 KV cache 测试 | 首张 `3321.23 ms`，后续 `2960.84 ms`，均值 `3005.89 ms` | 纯速度冠军。 |
| `omlx-kv-isolated-gemma-e4b-4bit` | `gemma-e4b-4bit` 批量 KV cache 测试 | 首张 `6873.89 ms`，后续 `5616.01 ms`，均值 `5773.25 ms` | 速度居中，比 `Qwen4` 快一些，但没 `e2b` 快。 |

## 直接可读的阶段性结论

如果你只看这批 benchmark，而不看 harness，那么更合理的结论是：

- 默认主路径优先候选：
  - `Qwen3-VL-4B-Instruct-4bit`
- 速度优先候选：
  - `gemma-4-e2b-it-4bit`
- 能跑但太慢：
  - `Qwen3-VL-8B-Instruct-4bit`
- 当前机器上不推荐：
  - `gemma-4-e4b-it-8bit`

## 最值得直接打开的原始文件

如果你只想开几份文件，不想全翻，优先看这些：

- `artifacts/benchmarks/omlx-five-models-single/best_candidates.json`
- `artifacts/benchmarks/omlx-five-models-single/20260409-225815/summary.json`
- `artifacts/benchmarks/omlx-kv-isolated-gemma-e2b/best_candidates.json`
- `artifacts/benchmarks/omlx-kv-isolated-qwen4/best_candidates.json`
- `artifacts/benchmarks/omlx-single-isolated-qwen8/best_candidates.json`
- `artifacts/benchmarks/omlx-single-isolated-gemma-e4b-8bit/best_candidates.json`

## 怎么把 benchmark 和 harness 结合起来看

推荐顺序还是：

1. 先用 benchmark 看请求层稳不稳、快不快
2. 再用 harness 看真实照片输出值不值得信
3. 最后才决定默认模型和 `model_profiles`

简单说：

- benchmark 决定“能不能跑、快不快”
- harness 决定“跑出来有没有实际价值”
