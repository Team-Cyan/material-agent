# OMLX Harness Runbook

这份文档是写给“不想读代码，但想稳定比较本地模型效果”的人看的。

你可以把它理解成：`material-agent` 的真人可读版模型对比手册。

## 一句话理解

- `omlx-benchmark` 看请求层稳不稳、快不快。
- `omlx-harness` 看真实 RAW 样片跑完整工作流后，输出值不值得信。

## 什么时候先跑 benchmark，什么时候直接跑 harness

### 先跑 `omlx-benchmark`

当你在调这些东西时，先跑 benchmark：

- `contract_mode`
- `prompt_preset`
- token cap
- temperature
- 图片缩放、JPEG 质量

原因：

- 这些属于请求层。
- 如果请求层本身就不稳，先讨论照片点评质量没有意义。

如果你只是想先快速理解仓库里已经跑过的 benchmark 历史结果，可以直接看：

- [docs/omlx-benchmark-matrix.md](omlx-benchmark-matrix.md)

### 再跑 `omlx-harness`

当你在调这些东西时，重点看 harness：

- `omlx.model_profiles.<model_id>`
- 美学 prompt
- 组点评 / 后期建议 prompt
- `domain/commentary.py` 里的质量护栏
- 默认主模型到底选哪个

原因：

- harness 会复用真实 `material-agent run` 路径。
- 它看到的是你日常真正会用到的行为，不是实验室里的缩减版。

如果你想先理解 `model_profiles` 到底是什么，再回来跑 harness，可以先看：

- [docs/omlx-model-profiles.md](omlx-model-profiles.md)

## 推荐工作流

1. 先确认桌面版 `oMLX.app` 正常工作。
2. 跑一次 benchmark，先确认请求结构和延迟没有明显问题。
3. 用固定样片跑 harness。
4. 只改一件事。
5. 用同一批样片再跑一次 harness。
6. 比较两次 `report.md` 和 `summary.json`。

## 最常用命令

```bash
# 先把 shared desktop runtime 拉起来
uv run material-agent omlx-start --config config.yaml --restart-shared

# 请求层 benchmark
uv run material-agent omlx-benchmark \
  --config config.yaml \
  --models Qwen3-VL-4B-Instruct-4bit \
  --sample-set /Users/lancer/materials/photos

# 真实样片 harness
uv run material-agent omlx-harness \
  --config config.yaml \
  --models Qwen3-VL-4B-Instruct-4bit gemma-4-e2b-it-4bit \
  --sample-set /Users/lancer/materials/photos \
  --limit 12
```

## harness 会产出什么

默认输出目录：

- `artifacts/harnesses/omlx/<timestamp>/`

里面最重要的是这些文件：

- `summary.json`
  顶层机器可读汇总
- `report.md`
  顶层人类可读报告
- `run_request.json`
  这次到底是拿什么参数跑的
- `config_snapshot.json`
  顶层配置快照
- `sample_manifest.json`
  这次实际用到的样片清单
- `<model>/summary.json`
  单个模型的机器可读结果
- `<model>/report.md`
  单个模型的人类可读结果
- `<model>/config_snapshot.json`
  该模型实际运行时的配置快照
- `<model>/runtime_status.before.json`
  跑之前采到的 shared/dedicated runtime 状态
- `<model>/runtime_status.after.json`
  跑完后再采一次，用来看 linked models / served models 有没有漂

你平时如果只是想快速判断，不一定要打开 `runtime_status*.json`。

现在每个模型自己的 `report.md` 里也会直接给：

- `Runtime mode after`
- `Shared desktop running after`
- `Runtime interpretation`

其中 `Runtime interpretation` 就是把那组 runtime JSON 翻译成人话后的结论。

另外，multi-model harness 跑完后会尝试把 shared desktop runtime 恢复回你原始配置里的默认模型集合。
这部分结果会写进顶层 `summary.json` / `report.md` 的 `restore_summary`。

## 看 report 时先看哪 5 个字段

### 1. `verdict`

这是报告最重要的结论字段。

- `ready_for_default_path`
  这批样片跑下来结构稳定、质量护栏没报警，可以作为默认主路径候选。
- `needs_prompt_refine`
  结构基本可用，但输出复读偏多，应该先调 prompt/profile。
- `needs_structural_fix`
  输出开始串味，比如后期建议里混入拍摄建议，这时先修结构，不要先争论审美。
- `runtime_unstable`
  先修运行时、probe 或请求稳定性，再谈模型好坏。

### 2. `primary_risks`

这是“为什么判成这个 verdict”的摘要，不用你自己从几十个数字里反推。

### 3. `action_hint`

这是下一步建议。

简单理解：

- `runtime_unstable`：先修 OMLX runtime / probe / request
- `needs_structural_fix`：先收紧 prompt 或 commentary guard
- `needs_prompt_refine`：先做 prompt/profile 调优
- `ready_for_default_path`：可以进入默认主路径候选

### 4. `invalid_post_count`

它表示后期建议里有没有串进不该出现的内容，比如：

- 拍摄时
- 三脚架
- 机位
- 组内问题

这个值理想情况应该是 `0`。

### 5. `max_post_repeat` / `max_group_repeat`

它表示整批样片里是否被同一句模板刷屏。

经验上：

- `1` 或 `2` 通常可接受
- `3+` 说明复读已经比较明显，应该调 prompt 或 commentary fallback

### 6. `shared_runtime_drift_detected`

这个字段是专门给桌面版 `oMLX.app` 加的。

如果它是 `true`，意思是：

- 这次候选模型虽然被请求了
- 但 shared runtime 的 linked/pinned model set 没有完全跟上

这时你应该把它理解成：

- 结构质量判断仍然有参考价值
- 但速度、缓存命中和“当前真正常驻 load 的模型是谁”这些结论不能直接下

### 6.5 `effective_model_set_matches` / `served_models_catalog_superset`

这两个字段主要是为了 shared desktop `oMLX.app`。

- `instance_matches`
  还是最严格的判断，要求 `served == linked == expected`
- `effective_model_set_matches`
  只要 `linked == expected` 且 `served` 没缺这些模型，就会是 `true`
- `served_models_catalog_superset`
  表示 `/v1/models` 看起来像“安装目录清单超集”，不应该直接当作 live pinned set

如果你在 shared desktop runtime 上看到：

- `instance_matches=false`
- `effective_model_set_matches=true`
- `served_models_catalog_superset=true`

通常更合理的解释是：

- 这次候选模型和 linked/pinned set 是对上的
- 只是 `served_models` 这个接口把更多已安装模型也列出来了

### 6.8 `Runtime mode after` / `Shared desktop running after` / `Runtime interpretation`

这是为了让你不用自己拼装 runtime 结论。

- `Runtime mode after`
  - 告诉你这次 harness 跑完后，当前看见的是 `shared_desktop` 还是 `dedicated`
- `Shared desktop running after`
  - 只有 `shared_desktop` 时最有意义
  - 它是 `false` 时，先别信这次对比
- `Runtime interpretation`
  - 这是 report 直接给出的“人话版结论”
  - 比如它写：
    - `shared desktop runtime looks aligned; /v1/models appears to include installed-model catalog extras.`
  - 你就可以直接理解成：
    - linked/pinned 模型集合已经对上候选模型
    - 只是 `/v1/models` 把额外已安装模型也列出来了

### 7. `restore_summary`

这个字段告诉你：

- harness 对比结束后，是否把桌面版 shared runtime 恢复回默认配置
- 最终恢复到了哪些 `active_models` / `linked_models`

现在顶层 `report.md` 的 `Restore` 区也会直接把这件事翻译成人类可读字段：

- `Restored`
- `Restarted`
- `Restore active models`
- `Restore linked models`
- `Restore drift detected`

如果你日常默认跑的是 `Qwen3-VL-4B-Instruct-4bit`，这里应该最终回到 Qwen。

## 如果报告不理想，先改哪里

### 运行前就不稳

先看：

- `src/material_agent/app/omlx_instance_service.py`
- `src/material_agent/adapters/models/omlx/probe.py`
- `src/material_agent/commands/scoring.py`

### JSON 结构或点评边界经常坏

先看：

- `src/material_agent/clients/prompts.py`
- `src/material_agent/clients/omlx.py`
- `src/material_agent/domain/commentary.py`

### 能跑完，但点评太像模板

先改：

1. `config.yaml` 里的 `omlx.model_profiles.<model_id>`
2. `domain/commentary.py` 的质量护栏 / fallback 逻辑
3. 只有确实跨模型都一样时，才回头改 `prompt_preset`

## 建议的样片策略

- 样片不要太大，先用 8 到 20 张。
- 一旦准备用来对比 before/after，就尽量固定这批样片。
- 样片最好同时包含：
  - 人像
  - 室内
  - 城市 / 建筑
  - 细节 / 近景

这样能更容易看出 scene 识别和点评泛化问题。

## 一条最实用的原则

不要只看“哪条建议听起来更顺耳”。

先看：

1. 能不能稳定跑完。
2. 结构有没有越界。
3. 会不会模板化刷屏。
4. 然后才看速度和文字风格。
