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

一个 work directory 同时只允许一个 mutating CLI controller；`run`, rescore/rewrite/reset 等操作共享 run lock。容器入口脚本通过 photos read-only mount 与 work/appdata writable mount 的约定隔离源照片；Web index 本身写在应用状态库而非照片目录。普通 CLI `run` 使用 `MATERIAL_AGENT_WORK_DIR` 指定独立状态目录；`web` 和 `review-scores` 才有显式 `--work-dir` 参数。

Web API **没有应用层认证**，因此是 trusted-LAN operator surface。端口默认 8776，监听地址可配置；运行在 `0.0.0.0` 仅表示绑定全部网卡，不构成访问控制。不得将端口发布到 Internet 或不可信 VLAN。`/health` 成功也不证明任务可运行、共享锁空闲或 inference adapter 工作。

## Web 任务监督、重启与取消

R1 将任务控制拆成 manager 与私有 [`web_worker.py`](../../src/material_agent/app/web_worker.py) 监督进程。每个任务在 queued 状态落盘前创建两份私有文件租约：生命周期 FD 由 manager → supervisor → CLI 继承，控制 FD 只由 manager → supervisor 继承。关闭副本不会显式解锁其他持有者。manager 重启后核对文件身份和私有回执；生命周期仍被持有时不会发布终态。任务状态、回执和取消请求保存在 appdata 的 `web/workers/`，控制能力不出现在 API 返回中。

取消先写入私有请求，由原监督进程向自己尚未回收的 CLI 进程组发 SIGTERM。manager 不会根据保存的 PID 发信号。终态以实际退出结果为准：0 为 finished，130 为 cancelled；消费取消请求后被 SIGTERM 终止也为 cancelled，其余非零为 failed。取消请求与自然完成相撞时不会覆盖成功/失败结果。外部 SIGTERM 若被 CLI 转为 130，也正确显示 cancelled。

控制租约消失但 CLI 仍持生命周期租约时，状态为 `unknown`，API 明确拒绝无法执行的取消并阻止冲突启动；待生命周期释放后，没有终态回执则为 interrupted/退出未知。损坏、替换或不可读的租约/回执保持未知，损坏的 task snapshot 拒绝启动且保留原文件。旧 PID-only 记录无法授权取消。UI 的 unknown 行可提交取消请求，缺失控制器时会显示 API 错误；状态提示包含可用的失败原因。

这不保证任意监督进程或整棵进程树故障后都能自动停止 surviving CLI；关闭继承 FD 的后代不在该生命周期证据内。共享 `run.lock` 仍是 CLI 最终写入互斥。历史发现见 [review](../operations/2026-10-22-repository-review.md)，实现契约见 [Task Process Lifetime](../ai/modules/web-operations.md#task-process-lifetime)。

契约与测试：[Web operations](../ai/modules/web-operations.md)、[`tests/test_web_service.py`](../../tests/test_web_service.py)、[`tests/test_model_catalog_service.py`](../../tests/test_model_catalog_service.py)、[`tests/test_config_validator.py`](../../tests/test_config_validator.py)、[`tests/test_container_contract.py`](../../tests/test_container_contract.py)。
