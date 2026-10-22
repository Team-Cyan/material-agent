# 07 · Web、配置、模型与安全边界

## Web API 与 admin dashboard

Web 服务由 [`app/web_service.py`](../../src/material_agent/app/web_service.py) 的标准库 HTTP server 提供，静态页面在 [`web/`](../../src/material_agent/web/app.js)。主要 API 包括：

| API | 行为 |
| --- | --- |
| `GET /api/overview`, `GET /api/jobs` | runtime 汇总与最近 job |
| `GET /api/tasks`, `POST /api/tasks`, `POST /api/tasks/{id}/cancel`, `GET /api/tasks/{id}/log` | task 列表、启动/取消与受限日志尾部 |
| `POST /api/library/index`, `GET /api/library`, `GET /api/library/{id}`, `GET /api/library/{id}/thumbnail` | 索引、分页列表、详情与工作目录 thumbnail |
| `GET/PUT /api/config` | 脱敏展示、验证后更新 YAML |
| `GET /api/models`, `POST /api/models/{id}/install`, `POST /api/models/{id}/select`, `DELETE /api/models/{id}` | registry 模型操作 |
| `GET /health` | 进程健康响应，不是评分或设备健康证明 |

Library detail 从最新 job/job_file/`score_payload` 读取结果。thumb 路径通过 item ID 解析并校验落在配置 input root 内；缩略图在 work storage 生成。Web-started scoring task 固定带 `--dry-run`，只产生模拟输出和 appdata/runtime 写入。

## 配置读写、快照与备份

CLI `load_config()` 顺序为 YAML parse → `normalize_config()` → `apply_model_selections()` → `validate_config()`。旧 alias 或遗留字段可以归一化为 canonical config；不要把接受旧字段误读成它是当前主配置格式。校验覆盖字段类型、范围和兼容约束。

Web config PUT 把 request config 中 `[REDACTED]` 占位符恢复为当前私有值，写 private temporary YAML，再走 CLI 同一套 load/normalize/validate；验证成功后复制 `.web.bak` 备份并原子替换 active config。task 启动会把当前配置复制成任务专属 YAML，补入文件上限，再启动子进程，因此单次 config 修改不改变已生成的 task snapshot。runtime session config snapshot 做 `redact_secrets()`，避免常见凭据字段写入 SQLite。private config/task/log/backup 文件模式通常为 0600，目录 0700。

Web 的 ModelCatalogService 注册表目录固定在启动参数；评分 CLI 子进程 registry 由 config 解析。CLI `--registry-dir` 与 `model_management.registry_dir` 应保持一致，避免 UI 和 scorer 对资产视图不一致。

## Registry 生命周期

[`app/model_catalog_service.py`](../../src/material_agent/app/model_catalog_service.py) 只安装/选择 catalog 中校验过 checksum 且有 adapter 的模型。bundled image assets 不会由删除操作移除；managed assets 与 selection registry 属于 work/appdata。selection 把 model path 与 identity 注入有效配置，score cache identity 也可包含资产 digest。

当前保护只覆盖“当前选择的模型不能轻易删除”等已有逻辑，不覆盖正在跑的子进程可能已捕获但尚未 lazy-load 的旧模型 A。operator 选择 B 后删除 A 仍可能让活动任务丢失路径；这是 R2 未修复问题。强制删除的意义也不能越过活动 task 的安全保证，计划要求补齐协调与测试。

## 工作目录、权限与网络边界

一个 work directory 同时只允许一个 mutating CLI controller；`run`, rescore/rewrite/reset 等操作共享 run lock。容器入口脚本通过 photos read-only mount 与 work/appdata writable mount 的约定隔离源照片；Web index 本身写在应用状态库而非照片目录。CLI 可通过显式 `--work-dir` 设定独立状态位置。

Web API **没有应用层认证**，因此是 trusted-LAN operator surface。端口默认 8776，监听地址可配置；运行在 `0.0.0.0` 仅表示绑定全部网卡，不构成访问控制。不得将端口发布到 Internet 或不可信 VLAN。`/health` 成功也不证明任务可运行、共享锁空闲或 inference adapter 工作。

## 当前 Web lifecycle 例外

Web manager 启动时把持久化 snapshot 中 queued/running/cancelling 标成 `interrupted`，没有核验子进程 PID/进程组身份。旧 worker 存活时仍可能持 run lock，UI 却显示没有 active task；新 run 失败于锁冲突。不能只凭保存 PID 去 kill，PID 可能复用。R1 计划要求识别 owned worker、避免误发信号并与 lock/SQLite 终态协调，当前未实现。

此外，如果子进程收到 API 之外的 SIGTERM，CLI 可能正常写入 cancelled 结果但返回 130；manager 仍可能按普通非零退出将 Web status 设为 failed。API cancel 先置 cancelling，因此路径不同。状态语义见 01 章与 [review](../operations/2026-10-22-repository-review.md)。

契约与测试：[Web operations](../ai/modules/web-operations.md)、[`tests/test_web_service.py`](../../tests/test_web_service.py)、[`tests/test_model_catalog_service.py`](../../tests/test_model_catalog_service.py)、[`tests/test_config_validator.py`](../../tests/test_config_validator.py)、[`tests/test_container_contract.py`](../../tests/test_container_contract.py)。
