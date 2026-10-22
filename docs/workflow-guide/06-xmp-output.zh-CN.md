# 06 · XMP 输出与保护边界

## projection 内容与用户数据

[`ExifToolXMPWriter`](../../src/material_agent/adapters/metadata/exiftool_xmp.py) 构造机器 subject tags：`pj:score=...`、`pj:rank=rank/group_size`、`pj:group=...`，可选 `pj:decision=...` 和 `pj:boosted`；默认目标是 `xmp:Identifier`，同时为兼容/展示写入 Subject 与 Lightroom hierarchical subject。结果还可能含 `photoshop:Instructions`、`dc:Description` 和 `xmp:Rating`。

Writer 会读取现有 Subject、Identifier、hierarchical Subject，保留不带 `pj:` 前缀的用户关键词，并重建机器拥有的 tag。`material-agent:keep`、`material-agent:reject` 是 selection keyword，由 reset/clear 路径作为机器 selection 标记处理。rating 采用 0–5 星映射；缺 rating 或显式 numeric zero 才可填入，既存 nonzero rating 按 `preserved_nonzero` 保留。description/instructions 是写入方管理的字段，但清理路径还要跟 expected value 比对，避免清掉外部更新。

## projection 与真实写入顺序

1. `preview_projection()` 先读取现 sidecar、识别可保留用户关键词、检查 rating ownership，并产生计划 receipt；dry-run 使用这一步，不写文件。
2. 写入时在同目录创建临时文件，构建 XMP，再调用 ExifTool 写入。sidecar path 选已有 `.xmp` 或 `.XMP`，否则新建 `.xmp`。
3. writer 记录源 sidecar identity（文件身份/属性）并拒绝 symbolic link；写完后重核 identity。若外部在过程中改动/新建目标，拒绝覆盖。通过检查后以同目录原子 replace 提交临时 sidecar。
4. writer 返回 `committed` receipt；应用层记录 runtime artifact/event 和 processed `xmp_projection_ledger`，随后完成 processed score/payload 的 finalize。DB 更新与文件替换不是共同事务；系统崩溃或 SQLite 错误可使二者暂时不一致。

此原子性只限单个 sidecar 的替换动作，不意味着多照片事务，也不意味着 SQLite 与 XMP 一起提交/回滚。batch 可部分完成，下一次运行可核对每张照片状态，但没有自动的全库回滚。

## 安全守卫

受保护边界包括：非零用户 rating；非 `pj:` 用户关键词；无法解析/无法安全读取时 fail closed；symlink 拒绝；已有 sidecar 被并发修改、目标写入期间新建时拒绝替换；reset/rewrite 清除 scalar 字段时对比预期旧值，或只有明确强制选项才清；命令使用运行锁避免本程序多个 mutator 同时写同一工作区。新建/重写文件使用临时文件与 replace，尽量保留原 sidecar 未管理字段。

写范围要分清：

| 操作 | 会写照片库中的 XMP 吗 | 其他影响 |
| --- | --- | --- |
| `run` 正常写出 | 会，逐张 sidecar | runtime 状态与 processed cache/receipt |
| `run --dry-run` / Web task | 不会 | runtime jobs/artifacts/logs/task state |
| `rewrite-xmp` 正常模式 | 会，按目标重建/清理机器投影 | processed projection ledger/runtime 诊断 |
| `rewrite-xmp --dry-run` | 不会 | 读取 sidecar/SQLite 并输出计划结果；不写 projection ledger |
| `reset-ai`（默认） | 不会清 XMP | 默认会清理 AI processed 状态；`--dry-run` 只报告，`--clear-xmp` 才额外清 sidecar |
| benchmark/review diagnostics | 不会 | 写实验或报告目录，不是生产投影 |

“只改 appdata”操作仍会写数据库、日志、索引、缩略图或模型文件；Web dry-run 不是完全只读系统动作。

## 当前已知 receipt 错误报告缺陷

`rewrite_xmp_service` 可能已成功原子替换 sidecar 并取得 `committed` receipt，随后 `record_xmp_projection()` 抛错。当前 catch 路径会尝试再记录 receipt，并输出 `ERROR writing <sidecar>`、计入 err；这会把 **DB receipt/persistence 阶段失败**说成 XMP 文件写失败。整体 bookkeeping 失败仍应被报告，但不应误称 sidecar 未提交。R4 follow-up 要求保留 committed receipt 与失败阶段并禁止自动重写；截至快照仍未修复。不要为补 receipt 自动重放已提交 writer。

## 定位

- [XMP writer 契约](../ai/modules/xmp-writer.md)
- [`adapters/metadata/exiftool_xmp.py`](../../src/material_agent/adapters/metadata/exiftool_xmp.py)、[`app/rewrite_xmp_service.py`](../../src/material_agent/app/rewrite_xmp_service.py)、[`app/review_runtime.py`](../../src/material_agent/app/review_runtime.py)、[`adapters/state/processed_sqlite.py`](../../src/material_agent/adapters/state/processed_sqlite.py)
- [`tests/test_writer.py`](../../tests/test_writer.py)、[`tests/test_app_services.py`](../../tests/test_app_services.py)、[`tests/test_xmp_projection_ledger.py`](../../tests/test_xmp_projection_ledger.py)、[`tests/test_xmp_preflight_errors.py`](../../tests/test_xmp_preflight_errors.py)
- 有限原生/恢复/Bridge 证据：[2026-10-15](../operations/2026-10-15-native-runtime-acceptance.md)、[2026-10-20 Bridge roundtrip review](../operations/2026-10-20-bridge-roundtrip-review.md)。通过有限 clean NEF/Bridge 场景，不等于任意格式或软件兼容。
