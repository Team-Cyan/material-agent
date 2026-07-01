# material-agent 模块地图

这份文档是给“不想先读代码实现，但想知道系统到底怎么跑”的人准备的。

你可以把它当成仓库的人类版结构图。

## 一句话理解

`material-agent` 会把一批 RAW 照片做完分组、评分、点评，然后把结果写回 XMP sidecar，并把完整历史保存在 SQLite 里。

## 执行 `make run` 时到底发生了什么

1. CLI 在 `shells/cli/main.py` 定义参数并读取 `config.yaml`，校验配置是否合法。
2. 如果后端是 OMLX，会先检查本地运行时，并同步 shared desktop runtime 的 active models。
3. 扫描输入目录里的 RAW 文件。
4. 先按时间分组，再按配置决定是否做视觉相似合并。
5. 解码每张图，计算技术分、快速预筛分、审美分，并输出最终 `total_score`、`decision`、`scene`。
6. 生成组级点评。
7. 生成单图后期建议。
8. 写 XMP sidecar。
9. 以最终写入的方式把分数、commentary 和 `done` 状态一起落到 SQLite，保证下次可以续跑而不是从零开始。
10. 根据整批结果把 runtime job/session 标成 `finished`、`finished_with_errors` 或 `failed`。

## 目录地图

| 路径 | 你可以把它理解成什么 | 里面主要放什么 |
|------|----------------------|----------------|
| `shells/cli/` | 命令行入口 | `main.py`、argparse、子命令分发 |
| `commands/` | 命令翻译层 | `run` / `omlx-start` / `omlx-benchmark` / `omlx-harness` 的薄封装，不重复定义 CLI parser |
| `app/` | 运行时骨架 | `review_service.py`、`review_runtime.py`、`omlx_instance_service.py`、benchmark/harness service |
| `domain/` | 业务规则层 | `scoring_engine.py`、`commentary.py`、`grouper.py`、`layered_decision.py` |
| `adapters/` | 外部系统接入层 | SQLite、ExifTool、OMLX/Ollama transport |
| `io/` | 输入输出辅助 | 文件扫描等工具 |
| `tests/` | 回归保护网 | 命令测试、pipeline 测试、runtime 测试 |
| `docs/ai/` | 给 AI 的项目知识库 | 模块说明、playbook、checklist、长期记忆 |

## 最重要的几个模块

### `commands/scoring.py`

- 真正的 `material-agent run` 命令入口
- 负责 CLI 参数覆盖、配置校验、OMLX preflight
- `run` 的 argparse 定义归 `shells/cli/main.py` 所有，这里只消费解析后的参数
- 然后把任务交给 review runtime

### `app/review_service.py`

- 负责一次完整 review 会话
- 创建 session/job
- 在调用方没有提供文件列表时负责扫描文件
- 把执行权交给 review executor

### `app/review_runtime.py`

- 整个 review 流程的“接线板”
- 把 grouping、scoring、commentary、XMP writing 接起来
- 如果你只想看一份文件就理解主流程，这份最值得看

### `domain/scoring_engine.py`

- 真正决定每张图怎么打分
- 输出 technical、screening、aesthetic、aggregate 分层信号
- 后面的 `keep / review / reject` 都建立在它的结果上

### `domain/commentary.py`

- 负责组点评输入构造
- 负责单图后期建议输入构造
- 负责 fallback 和质量护栏
- 避免模型输出掉成裸分数字串，或者把拍摄建议混进后期建议

### `adapters/state/processed_sqlite.py`

- 负责最终结果持久化
- 保存分数、scene、decision、commentary、signals
- `done` 终态写入会和 commentary 一起落库，避免“状态已完成但点评没写全”的恢复断层
- 这是“这张图到底处理完没有”的最终依据

### `app/omlx_instance_service.py`

- 管 shared / dedicated OMLX runtime
- 管 active model set 同步
- 管 shared desktop runtime 重启
- `omlx-status` 的诊断信息也主要来自这里

### `app/omlx_benchmark_service.py`

- 负责请求层 benchmark
- 适合比较 schema 稳定性、token cap、temperature、KV cache 行为
- 不适合直接代替真实照片输出判断

### `app/omlx_harness_service.py`

- 负责真实样片 harness
- 不走伪造 benchmark 路径，而是复用真实 `run`
- 输出 JSON + Markdown 报告，方便比较模型和 prompt 配置

## 什么时候用哪个工具

### 用 `omlx-benchmark` 的时候

- 你在调请求结构
- 你在比较 `contract_mode`
- 你在看 latency / schema success
- 你在调 token cap、temperature、图片缩放

### 用 `omlx-harness` 的时候

- 你想看真实照片跑出来的结果到底值不值得信
- 你想抓点评复读问题
- 你想抓组点评退化或后期建议越界
- 你想拿一批固定样片做 before/after 比较

## 如果感觉哪里不对，先看哪

### 模型输出结构经常坏

- `src/material_agent/clients/prompts.py`
- `src/material_agent/clients/omlx.py`
- `src/material_agent/domain/commentary.py`

### 任务在真正处理照片前就失败

- `src/material_agent/commands/scoring.py`
- `src/material_agent/app/omlx_instance_service.py`
- `src/material_agent/adapters/models/omlx/probe.py`

### 分数出来了，但 XMP 或 DB 写得不对

- `src/material_agent/app/review_runtime.py`
- `src/material_agent/adapters/metadata/exiftool_xmp.py`
- `src/material_agent/adapters/state/processed_sqlite.py`
- 如果批次最后显示 `finished_with_errors`，优先看 `review_photos.py` 的逐文件错误累计和 runtime events

### 模型对比总是凭感觉，不够可重复

- 用 `omlx-benchmark` 看请求层
- 用 `omlx-harness` 看真实样片输出
- 把结果沉淀在：
  - `artifacts/benchmarks/omlx/`
  - `artifacts/harnesses/omlx/`

## `docs/ai/` 是什么

如果以后你继续让 AI 帮你改这个项目，`docs/ai/` 是项目内部的 AI 知识库，不是临时笔记。

最重要的几个入口是：

- `docs/ai/README.md`
- `docs/ai/architecture/module-boundaries.md`
- `docs/ai/modules/review-pipeline.md`
- `docs/ai/modules/omlx-runtime.md`
- `docs/ai/modules/omlx-harness.md`

如果你此刻的目标不是“继续看模块”，而是“看懂模型对比报告”，下一份该读的是：

- [harness-runbook.md](harness-runbook.md)
