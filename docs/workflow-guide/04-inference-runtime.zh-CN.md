# 04 · 推理生命周期与资源

## 后端、设备与 fallback

`backend: local` 是产品默认主路径；local client 组合传统技术评分、本地启发式 vision 与按需加载的 learned adapters。runtime 配置可请求 OpenVINO device，并在设备不可用且规则允许时尝试 fallback device。`OpenVinoSession` 会分别记录 requested、compiled/compile target 与 OpenVINO 回读的 execution devices；若属性读取失败，实际设备字段保持 unknown 并记录 readback error，不能用请求值替代实际证据。

CPU 是必要 fallback 和默认安全基线。OpenVINO 是 Intel 优先加速路径；通过某台 Intel CPU 的编译或某个 accelerator 设备可用，不代表其他 GPU、驱动、容器或 RAW 组合都支持。`config.yaml` 顶部也明确特定 Intel 主机曾选择 CPU；这里只能说明不能假设 GPU 更快。

`local` 可选模块未启用时不导入其可选依赖。`enforce_available: false` 时缺模型、包或执行资源会产生有来源的 fallback evidence；强制启用时则失败显式暴露。降级 metadata 与正常预测必须区分。

## 生命周期与缓存

[`adapters/models/openvino_session.py`](../../src/material_agent/adapters/models/openvino_session.py) 在 session 初始化时读取模型资产、编译模型并创建 bounded infer queue；`run()` 用锁保持一次有序执行，按 batch/window 预处理和分批推理。模型编译缓存带模型/runtime/target/batch/strategy/performance hint identity；自己的 cache namespace 通过文件锁保护，最多维护 16 项或 2 GiB，并按旧目录清理。

[`inference_contract.py`](../../src/material_agent/adapters/models/inference_contract.py) 提供模型资产快照与身份信息。OpenVINO NIMA、SSD、embedding 共用 session 能力，但每个 adapter 的前处理、后处理和证据语义仍独立。NIMA/SSD/embedding 可能在首个需要的照片上 lazy-load/compile；因此选模型后的 effective config 路径并不等于资产已在该任务开始前安全锁定。当前模型删除 race 是已确认问题：Web 任务运行时可先把模型 A 路径写入 config，随后切到 B 并删除 A；首个 lazy load 可能失败或非强制时 fallback。R2 计划尚未实现对活动任务所引用资产的 lease/阻止删除。

按图像结果缓存、processed score cache、编译产物 cache 是不同层次：

- compiled cache 复用模型编译产物；
- client/local embedding result cache 的 key 含模型、预处理和 runtime identity，并限制内存；
- processed score cache 通过 config revision、依赖版本和模型资产 identity 判断可否跳过整张照片评分。

缓存命中只说明被纳入 identity 的输入相符，不是新的模型推理证据。

## 准备窗口与内存观测

`ReviewPhotosJob` 使用可配置 `score_prefetch_window`（构造器夹在 1..32；当前配置为 2），分阶段 prepare/prime/score，并尽量限制同时持有的 RAW 预览。启用 aesthetic/embedding 时可对准备好的 frames 提前批量 prime；如果 screening 开启则跳过该 prime 分支。shared OpenVINO 一轮准备窗口最多约 32 张（受 declared batch 影响）。这些界限表达的是应用层调度，不是进程内存硬上限。

`preparation_memory.py` 只采样可识别的 `RawFrame` 和 jpeg/gray/pixels/focus_gray 缓冲，区分逻辑 nbytes、可识别 owner payload bytes、RSS 与 lifetime high-water。它不观测所有 Python/native/model tensor 内存，也不是完整瞬时峰值；unknown 采样应按 unknown 读取，而不是补零。job 写出 `Preparation memory diagnostics` 日志，不将其伪装成性能改进。不存在可由该日志直接推出吞吐提升的结论。

## 资源与工具

`prepare-openvino-model` 将 ONNX 外部数据物化到同一 bundle 路径并生成 digest `bundle.json`；编译缓存另有版本化目录。受管理 registry 只接受 checksum 固定且有 adapter 支持的条目。私人模型路径与真实推理资源不能写入公共文档。

- [inference runtime 契约](../ai/inference-runtime.md)
- [local model stack 契约](../ai/modules/local-model-stack.md)
- [`openvino_session.py`](../../src/material_agent/adapters/models/openvino_session.py)、[`inference_contract.py`](../../src/material_agent/adapters/models/inference_contract.py)、[`preparation_memory.py`](../../src/material_agent/app/preparation_memory.py)
- [`tests/test_inference_lifecycle.py`](../../tests/test_inference_lifecycle.py)、[`tests/test_openvino_model_service.py`](../../tests/test_openvino_model_service.py)、[`tests/test_preparation_memory.py`](../../tests/test_preparation_memory.py)
- 编译/目标状态应以对应模型运行记录为证据；benchmark 结果仅适用于其固定资产、输入、设备和镜像边界。
