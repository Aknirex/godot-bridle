# godot-bridle 技术架构决策记录

> **文档版本**：v0.1
> **创建日期**：2026-06-18
> **阶段**：概要设计前置决策
> **依赖文档**：
> - [02-requirements-analysis.md](02-requirements-analysis.md) v0.2
> - [03-provider-research-and-tech-stack.md](03-provider-research-and-tech-stack.md) v0.1
> **状态**：建议采纳

---

## 1. 架构定位

Bridle 被确认定位为：

> 面向 Godot 游戏开发的桌面端垂直 Harness。

它不是通用聊天客户端，不是 Web SaaS，不是 Godot 编辑器插件，也不是单一 AI 供应商的封装。核心职责是把 LLM、3D 模型、纹理、绑定、动画等外部生成能力，通过 BYOK 和统一 Provider 能力模型接入，再稳定落地到 Godot 项目。

---

## 2. 已确认决策

### ADR-001：产品形态采用桌面应用优先

**决策**：MVP 必须是桌面应用。CLI 只作为测试、自动化、调试和未来 CI 的薄接口。避免 local Web UI 成为主要体验。

**首选方案**：Tauri v2 + Python sidecar。

**备选方案**：PySide6。

**理由**：

- 用户明确希望使用桌面软件；
- Bridle 需要与 Godot 编辑器并排工作；
- BYOK、项目选择、进度、日志、资产结果和设置都更适合桌面交互；
- Tauri 比 Electron 更轻，适合工具类桌面软件；
- Python sidecar 能保留 AI、资产处理和 Godot 管线生态。

**约束**：

- MVP UI 功能保持克制，不做复杂 Web 后端；
- 桌面层只调用 application service，不直接操作 Provider 或 Godot 文件。

---

### ADR-002：核心业务层采用 Python 3.11+

**决策**：核心 Harness、Provider facade、资产管线、Godot 项目处理使用 Python 3.11+。

**理由**：

- LiteLLM、Pydantic、httpx、trimesh、pygltflib、pytest 等生态成熟；
- Python 更适合快速实现多 API 编排和资产处理原型；
- Godot CLI、文件系统、GLB 检测和测试工具链接入直接。

**约束**：

- Python core 必须是 UI 无关的包；
- 所有可被桌面调用的功能通过 `bridle.app.services` 暴露；
- 长任务必须通过 job/event 模型向桌面层报告进度。

---

### ADR-003：LLM Provider 不自研，MVP 复用 LiteLLM SDK

**决策**：MVP 使用 LiteLLM SDK 作为 LLM Provider 基础层。Bridle 不从零实现 DeepSeek/OpenAI/Claude/Gemini/Ollama 等 LLM Provider。

**MVP 默认 LLM**：DeepSeek。

**默认模型建议**：

- 普通任务：`deepseek/deepseek-chat`
- 推理任务：`deepseek/deepseek-reasoner`

**理由**：

- LiteLLM 已覆盖大量 LLM Provider；
- DeepSeek 已有现成支持；
- 支持 streaming、错误映射、fallback、budget/cost 等后续需要的能力；
- 符合“多参考和整合先进 Harness”的目标。

**Bridle 仍需自研的部分**：

- `LLMProviderFacade`；
- Bridle 统一 `LLMEvent`；
- BYOK Key 解析、脱敏和连接测试；
- Provider capability 声明；
- DeepSeek reasoning metadata 保留；
- UI 进度和日志事件。

---

### ADR-004：资产 Provider 抽象自研

**决策**：3D 模型、纹理、绑定、动画等 Asset Provider 抽象由 Bridle 自研。

**理由**：

- 资产生成 API 没有像 OpenAI-compatible 一样的事实标准；
- 不同供应商任务模型差异大：同步、异步 job、webhook、轮询、文件 URL、对象存储下载等；
- 游戏资产落地需要 Godot 特有的格式、目录、材质和导入逻辑。

**MVP 首个 Provider**：Meshy。

**后续验证 Provider**：

- Tripo：第二个 3D Provider；
- fal.ai/Hunyuan3D：聚合型/本地优先方向；
- DeepMotion：AnimationProvider；
- Polycam/ArmorLab：TextureProvider。

---

### ADR-005：采用能力模型而不是供应商分支

**决策**：Provider 通过 capability 声明能力，工作流模板只依赖能力，不依赖具体供应商。

**核心能力类型**：

- `llm.chat`
- `llm.stream`
- `llm.structured_output`
- `model3d.text_to_3d`
- `model3d.image_to_3d`
- `texture.retexture`
- `texture.pbr_generate`
- `rigging.auto_rig`
- `animation.video_to_motion`
- `animation.text_to_motion`

**理由**：

- 防止 Meshy/DeepSeek 逻辑泄露到工作流；
- 为更多供应商兼容留下空间；
- 支持同一工作流在不同 Provider 组合下执行。

---

### ADR-006：异步任务编排引擎是 P0 核心组件

**决策**：Bridle 自研异步任务编排引擎（Async Task Orchestrator），作为 Python sidecar 的 P0 核心组件。所有长耗时操作必须提交为后台 job 执行，桌面层只订阅事件和查询状态，不直接同步等待 Provider 或 Godot CLI 调用。

**必须异步编排的任务**：

- Meshy/Tripo/Hunyuan3D 等 3D 生成任务；
- 资产生成 Provider 的轮询、webhook 等待和重试；
- 大文件下载、校验、解压和内容哈希；
- GLB 检测、材质解析、贴图整理；
- Godot CLI / headless 导入和校验；
- LLM 流式响应和长上下文代码生成；
- 批量处理多个资产或多个纹理变体。

**理由**：

- Meshy 生成 3D 模型通常需要 20 秒到数分钟；
- Godot CLI 导入大型 GLB 会阻塞数秒甚至更久；
- 如果 Python sidecar 用同步阻塞调用，Tauri 前端会表现为无响应、进度不可见、无法取消；
- 长任务需要可取消、可恢复、可重试、可诊断，而普通函数调用模型不够。

**运行模型**：

- 桌面 UI 调用 `submit_job(...)`，立即返回 `job_id`；
- Python sidecar 在后台事件循环或 worker 中执行任务；
- UI 通过事件流订阅 `JobEvent`；
- UI 可随时查询 `get_job_status(job_id)`；
- UI 可请求 `cancel_job(job_id)`；
- job 状态持久化到 SQLite；
- job 输出目录采用幂等路径，失败后可从阶段边界恢复。

**任务状态**：

- `created`
- `queued`
- `running`
- `waiting_provider`
- `downloading`
- `importing`
- `succeeded`
- `failed`
- `cancel_requested`
- `cancelled`
- `retrying`

**任务事件**：

- `job.created`
- `job.started`
- `job.progress`
- `provider.requested`
- `provider.polling`
- `provider.completed`
- `download.started`
- `download.progress`
- `godot_cli.started`
- `godot_cli.completed`
- `job.retrying`
- `job.failed`
- `job.succeeded`
- `job.cancelled`

**实现约束**：

- Tauri command 不允许直接执行长耗时任务；
- 所有 Provider 调用必须设置 timeout、retry 和 cancellation check；
- 所有 Godot CLI 调用必须通过异步 subprocess 或 worker 执行；
- 大文件下载必须支持分块进度；
- job store 每个阶段开始和结束都要落库；
- 任务事件必须可被桌面 UI、CLI 和测试同时消费；
- Python core 中同步阻塞库若不可避免，必须放入 worker thread/process，不能阻塞主事件循环。

**建议实现**：

- MVP 使用 `asyncio` + 有界 `asyncio.Queue` + worker pool；
- HTTP 使用 `httpx.AsyncClient`；
- Godot CLI 使用 `asyncio.create_subprocess_exec`；
- CPU/阻塞型 GLB 处理用 `asyncio.to_thread()` 或独立 worker；
- 持久化使用 SQLite job store；
- 后续如任务复杂度上升，再评估 `Prefect`、`Temporal`、`Dramatiq` 等外部编排器，但 MVP 不引入服务端依赖。

---

### ADR-007：工作流引擎自研轻量状态机

**决策**：Bridle 自研轻量 workflow/job state machine，运行在异步任务编排引擎之上，不直接采用 LangChain/LangGraph/Haystack 作为核心执行引擎。

**理由**：

- Bridle 的主流程是长耗时资产任务，不是通用 Agent loop；
- 需要可恢复、可重试、幂等输出目录、下载进度和导入阶段状态；
- 通用 Agent 框架可参考，但作为核心会引入不必要复杂度。

**可借鉴项目**：

- Haystack component/pipeline 思想；
- Pydantic AI 结构化输入输出；
- LangGraph 可恢复图执行思想；
- DSPy 后续用于 prompt/上下文优化。

---

### ADR-008：BYOK 是核心架构能力

**决策**：BYOK 不作为设置页附属功能，而是 Provider 系统的一等能力。

**MVP**：

- 环境变量读取；
- Provider 级 `api_key_env`；
- Key 脱敏展示；
- 连接测试；
- 错误分类；
- 日志脱敏。

**P1**：

- 系统钥匙串或本地加密存储；
- 用户级默认配置和项目级覆盖；
- 多 Key 轮换；
- 额度、余额、限流提示；
- 外部 Gateway URL。

---

### ADR-009：本地持久化采用 SQLite + 文件缓存

**决策**：MVP 使用 SQLite 存储项目、Provider 配置元数据、job 状态、运行记录和基准指标；资产文件和缓存文件落地到文件系统。

**可选库**：

- SQLite：标准库 `sqlite3` 或 SQLModel/SQLAlchemy；
- 缓存：diskcache 或自建内容哈希目录。

**理由**：

- 桌面软件不应依赖外部数据库；
- 长任务恢复需要持久化；
- 资产缓存天然适合文件系统；
- 后续导出诊断包更简单。

---

### ADR-010：Godot 集成顺序为 FS → Godot CLI → MCP

**决策**：MVP 优先实现文件系统桥接和 Godot CLI 校验，MCP 作为 P1/P2 增强。

**理由**：

- Godot 项目文件文本友好；
- 资产写入、目录管理、示例脚本生成可以先通过 FS 完成；
- Godot CLI 可用于导入校验和批处理；
- MCP 更适合实时编辑器交互，MVP 不必阻塞在 MCP 生态选择上。

---

### ADR-011：GLB 管线采用“检测优先，修复分级”

**决策**：MVP 不承诺万能 GLB 修复，采用检测、基础规范化、Godot 导入校验和明确错误提示。

**MVP 工具**：

- `trimesh`：几何检测；
- `pygltflib`：glTF/GLB 元数据与材质通道解析；
- Godot CLI：最终导入校验。

**MVP 能力**：

- 文件可解析；
- 尺寸/比例检查；
- 纹理路径和 PBR 通道识别；
- 输出目录规范化；
- 生成示例场景或引用脚本。

---

### ADR-012：配置采用 TOML + Pydantic Settings

**决策**：配置文件采用 TOML，运行时加载和校验使用 Pydantic Settings。

**理由**：

- Python 3.11 原生支持 `tomllib`；
- TOML 对用户可读，隐式类型少于 YAML；
- 适合桌面工具和项目级配置；
- Pydantic 可提供强类型校验和友好错误。

---

### ADR-013：观测与基准从 MVP 开始埋点

**决策**：MVP 先记录结构化事件和基准指标，P1 接 OpenTelemetry。

**MVP 指标**：

- LLM 首 token 延迟；
- LLM 总耗时；
- Provider 连接测试耗时；
- 缓存命中耗时；
- 资产 job 轮询耗时；
- 下载耗时；
- GLB 检测/导入耗时；
- 失败阶段和错误分类。

**理由**：

- Harness 性能目标需要可量化；
- 桌面用户出问题时需要诊断；
- 后续对标 LiteLLM/Bifrost/LangChain 等项目需要数据基础。

---

### ADR-014：Tauri 与 Python Sidecar 采用 stdio JSON-RPC

**决策**：MVP 中 Tauri 与 Python sidecar 的主通信协议采用 stdio JSON-RPC。备选方案为 localhost WebSocket/HTTP，仅在 stdio 无法满足事件流或调试需求时启用。

**理由**：

- Tauri 对 sidecar 进程模型支持自然，stdio 不需要额外端口；
- 避免 localhost HTTP/WebSocket 带来的端口冲突、防火墙提示和本机服务暴露面；
- JSON-RPC 足够表达 request/response、错误和方法版本；
- 事件流可以通过 JSON lines notification 实现；
- CLI 和测试可以复用同一 application service，而不要求运行 Web server。

**协议约束**：

- 每条消息为一行 UTF-8 JSON，即 JSON Lines；
- request 使用 JSON-RPC 2.0 风格：`jsonrpc`、`id`、`method`、`params`；
- response 必须包含同一 `id`；
- job 事件通过 notification 推送：无 `id`，`method = "job.event"`；
- 所有消息必须带 `protocol_version`；
- sidecar 启动后先发送 `sidecar.ready`；
- 长任务 command 只能返回 `job_id`，不能阻塞等待任务完成。

**备选条件**：

- 如果 Tauri stdio 对高频事件或二进制数据不合适，允许引入 localhost WebSocket 作为事件通道；
- localhost 通道必须绑定 `127.0.0.1`，使用随机端口和一次性 token；
- 不允许把 WebUI 或远程 HTTP API 作为 MVP 产品形态。

---

## 3. 总体架构

```
┌────────────────────────────────────────────┐
│ Bridle Desktop App                          │
│ Tauri v2 UI                                 │
│ - Project picker                            │
│ - BYOK settings                             │
│ - Workflow launcher                         │
│ - Progress / logs / asset results           │
└─────────────────────┬──────────────────────┘
                      │ desktop bridge
┌─────────────────────▼──────────────────────┐
│ Python Sidecar / Bridle Application Service │
│ - app.services                              │
│ - async task orchestration                  │
│ - event stream                              │
│ - config / key resolver                     │
└─────────────────────┬──────────────────────┘
                      │
┌─────────────────────▼──────────────────────┐
│ Bridle Domain Harness                       │
│ - typed domain models                       │
│ - async task orchestrator                    │
│ - workflow state machine                    │
│ - provider capability registry              │
│ - error taxonomy                            │
│ - cache / SQLite job store                  │
│ - benchmark event recorder                  │
└───────┬───────────────────────────┬────────┘
        │                           │
┌───────▼──────────────┐   ┌────────▼─────────────┐
│ LLM Provider Facade   │   │ Asset Provider Facade │
│ LiteLLM SDK           │   │ Meshy / Tripo / ...   │
│ DeepSeek default      │   │ Model/Texture/Rig/Anim│
└───────┬──────────────┘   └────────┬─────────────┘
        │                           │
┌───────▼───────────────────────────▼────────┐
│ External APIs / BYOK                         │
│ DeepSeek / OpenAI / Claude / Meshy / ...     │
└─────────────────────┬──────────────────────┘
                      │
┌─────────────────────▼──────────────────────┐
│ Godot Integration                            │
│ - FS bridge                                  │
│ - Godot CLI bridge                           │
│ - import / repair pipeline                   │
│ - MCP later                                  │
└────────────────────────────────────────────┘
```

---

## 4. 建议项目结构

```
godot-bridle/
├── bridle/
│   ├── app/
│   │   ├── services.py
│   │   ├── desktop_api.py
│   │   └── cli.py
│   ├── domain/
│   │   ├── assets.py
│   │   ├── capabilities.py
│   │   ├── config.py
│   │   ├── events.py
│   │   ├── jobs.py
│   │   └── llm.py
│   ├── harness/
│   │   ├── benchmark.py
│   │   ├── cache.py
│   │   ├── errors.py
│   │   ├── event_bus.py
│   │   ├── job_store.py
│   │   ├── task_orchestrator.py
│   │   ├── workers.py
│   │   └── workflow.py
│   ├── providers/
│   │   ├── base.py
│   │   ├── llm_litellm.py
│   │   └── asset_meshy.py
│   ├── config/
│   │   ├── key_resolver.py
│   │   └── settings.py
│   └── godot/
│       ├── cli.py
│       ├── import_pipeline.py
│       └── project.py
├── desktop/
│   └── tauri app
├── templates/
├── tests/
└── docs/
```

---

## 5. 与早期计划的差异

需要修正早期 `01-engineering-plan.md` 中的假设：

1. 不再手写 Claude/OpenAI Provider 作为 MVP 核心任务，改为 LiteLLM facade。
2. DeepSeek 是测试阶段默认 LLM。
3. 桌面应用不是后置项，MVP 即桌面优先。
4. local Web UI 不作为主路线。
5. CLI 只保留薄接口。
6. 配置从“YAML/TOML 待定”收敛为 TOML。
7. 语义缓存后置，MVP 先做精确缓存、内容哈希和 job store。
8. MCP 后置，MVP 先 FS + Godot CLI。
9. 异步任务编排引擎是 P0，所有长耗时 Provider/Godot/下载/导入任务必须后台执行。

---

## 6. 最终确认版技术栈

| 层级 | 确认选择 |
|---|---|
| 桌面壳 | Tauri v2 优先，PySide6 备选 |
| 前端 | TypeScript + 轻量组件体系 |
| Tauri ↔ Python 通信 | stdio JSON-RPC over JSON Lines |
| Python 核心 | Python 3.11+ |
| 依赖管理 | uv 优先，Poetry 备选 |
| LLM 适配 | LiteLLM SDK |
| 测试 LLM | DeepSeek |
| 资产 Provider MVP | Meshy |
| HTTP | httpx |
| 数据模型 | Pydantic v2 |
| 配置 | TOML + Pydantic Settings |
| Key P0 | 环境变量 + 脱敏 + 连接测试 |
| Key P1 | keyring / 系统钥匙串 |
| 持久化 | SQLite |
| 异步任务编排 | asyncio + bounded queue + worker pool |
| 文件缓存 | 内容哈希目录或 diskcache |
| 日志 | structlog |
| 观测 | 结构化事件 P0，OpenTelemetry P1 |
| GLB | trimesh + pygltflib + Godot CLI |
| Godot 集成 | FS + Godot CLI，MCP 后置 |
| 测试 | pytest + respx + vcr.py + pytest-benchmark |
| CLI | Typer 薄接口 |
