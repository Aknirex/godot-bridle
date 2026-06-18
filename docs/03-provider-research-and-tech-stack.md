# godot-bridle Provider 调研与技术栈选择草案

> **文档版本**：v0.1
> **创建日期**：2026-06-18
> **阶段**：需求分析 → 技术选型讨论
> **依赖文档**：
> - [02-requirements-analysis.md](02-requirements-analysis.md) v0.2
> **状态**：待评审

---

## 1. 调研结论

LLM Provider 层已有成熟开源项目，不建议 Bridle 从零实现多 LLM 适配。Bridle 应采用“复用 LLM Gateway/SDK + 自研 Bridle 领域抽象”的方式：

1. **LLM 调用层优先复用 LiteLLM 或 Bifrost**，避免重复实现 OpenAI、DeepSeek、Claude、Gemini、Ollama 等 Provider 适配。
2. **Bridle 自研的是领域 Harness**：工作流事件、Godot 上下文、资产生成任务、资产导入、缓存策略、BYOK UX 和插件规范。
3. **资产 Provider 层仍需自研抽象**，因为 3D 模型、纹理、绑定、动画供应商没有像 LLM 一样统一的事实标准。
4. **DeepSeek 测试阶段接入应走现成 LLM 适配层**，不单独手写完整 Provider。若使用 LiteLLM，可直接使用 `deepseek/deepseek-chat`、`deepseek/deepseek-reasoner` 等模型命名。
5. **技术栈应围绕 Python 核心包构建**，因为 Godot 项目处理、GLB/材质处理、API 编排、测试工具和 LiteLLM SDK 生态都更顺。

---

## 2. LLM Provider 候选

### 2.1 LiteLLM

定位：Python SDK + 可自托管 Proxy Server 的开源 AI Gateway。

可利用能力：

- 统一 OpenAI 风格接口调用 100+ LLM Provider；
- 支持 DeepSeek，并支持流式调用；
- 支持 retry/fallback、预算、成本跟踪、Provider 异常映射；
- 支持 SDK 嵌入，也支持独立 Proxy；
- Python 生态契合 Bridle 核心。

适合 Bridle 的地方：

- MVP 可以直接以 SDK 形式嵌入，减少部署复杂度；
- 后续如需要团队/企业模式，可切到 Proxy Server；
- DeepSeek 接入成本低；
- 支持 OpenAI-compatible 生态，适合 BYOK。

风险：

- Python 热路径性能可能弱于 Go/Rust 网关；
- 抽象层可能隐藏部分 Provider 特有能力；
- Bridle 仍需自行统一事件流、日志、UI 状态和本地 Key 管理。

建议：

> MVP 默认选 LiteLLM SDK 作为 LLM Provider 基础层。

### 2.2 Bifrost

定位：Go 实现的高性能 AI Gateway，OpenAI-compatible API，强调低延迟、高吞吐、自动 failover 和负载均衡。

可利用能力：

- 多 Provider 统一 OpenAI-compatible API；
- 自动 failover、load balancing、semantic caching；
- 内置 Web UI 配置和监控；
- 性能目标强，适合作为后续对标对象或高性能模式。

适合 Bridle 的地方：

- 与“最终 Harness 性能高于主流平均水平”的目标相符；
- 可作为 Bridle 的可选外部 LLM Gateway；
- 适合未来多用户、团队或高并发场景。

风险：

- Go 网关作为 sidecar 会增加桌面应用打包和进程管理复杂度；
- MVP 阶段 Bridle 的瓶颈大概率在外部 API 生成、资产下载和导入，不在 LLM Gateway 微秒级开销；
- LLM-only，不能解决资产 Provider 和 Godot 管线。

建议：

> Bifrost 不作为 MVP 默认依赖，但作为 Phase 2 性能对标和可选 Gateway 后端。

### 2.3 Portkey AI Gateway

定位：开源 AI Gateway，强调 guardrails、路由、重试、fallback、负载均衡、MCP Gateway 和多模态。

可利用能力：

- OpenAI-compatible 客户端；
- 路由、重试、fallback、guardrails；
- 多模态和 MCP 方向值得借鉴；
- MIT license。

适合 Bridle 的地方：

- BYOK、可观测、guardrails 和 MCP Gateway 思路有参考价值；
- 更偏平台化/网关化，适合企业版方向。

风险：

- 对桌面本地应用可能偏重；
- Hosted/Cloud 方案与 Bridle 本地优先和 BYOK 隐私定位不完全一致；
- 仍不能覆盖游戏资产生成和 Godot 导入。

建议：

> 暂不作为核心依赖，作为 BYOK、guardrails、MCP Gateway 设计参考。

### 2.4 LangChain / LangGraph

定位：LLM 应用框架，Provider 集成生态非常广，已有 DeepSeek 集成包。

可利用能力：

- `langchain-deepseek` 支持 DeepSeek；
- 大量 Provider 集成；
- 工具调用、结构化输出、agent/workflow 能力成熟。

适合 Bridle 的地方：

- 如果未来需要复杂 Agent 或工具链编排，可引入 LangGraph；
- 可参考 Provider 标准接口和集成方式。

风险：

- 对 MVP 的“资产管线 + 本地桌面 Harness”可能过重；
- 依赖层级大，升级变动可能影响稳定性；
- LangChain 的抽象不是专为长耗时资产任务设计。

建议：

> 不作为 MVP 核心 Harness，局部参考其 Provider/工具接口；复杂 agent 编排阶段再评估 LangGraph。

---

## 3. 资产生成 Provider 候选

### 3.1 Meshy

能力：

- Text-to-3D；
- Image-to-3D；
- AI Texturing / Retexture；
- Remesh；
- Rigging and Animation；
- Webhook support。

特点：

- Text-to-3D 是 preview → refine 两步任务；
- 输出适合游戏资产管线验证；
- 能覆盖 MVP 角色生成的大部分链路。

建议：

> MVP 首个 Asset Provider。Bridle 需要把 Meshy 的两阶段任务抽象为统一 `AssetJob`。

### 3.2 Tripo

能力：

- Text-to-3D；
- Image-to-3D；
- Multiview-to-3D；
- GLB 输出；
- 可选 PBR、quad remeshing、low-poly 等能力。

建议：

> Phase 1 后半或 Phase 2 作为第二个 3D Provider，用于验证 Bridle 资产 Provider 抽象不是 Meshy-only。

### 3.3 Hunyuan3D via fal.ai / 本地 API

能力：

- Image-to-3D；
- 部分版本支持高质量几何、PBR、商用推理；
- fal.ai 提供统一 serverless API；
- Tencent Hunyuan3D 开源项目提供本地/自托管可能。

建议：

> Phase 2 Provider。fal.ai 路线可验证“聚合型资产模型平台”，本地 Hunyuan3D 路线可验证“本地优先/私有部署”。

### 3.4 DeepMotion

能力：

- Video-to-3D animation；
- REST API；
- 输出 FBX、BVH 等动画格式；
- 支持自动 retargeting 到自定义角色。

建议：

> Phase 2/3 AnimationProvider。MVP 只需在接口设计中预留 `AnimationProvider` 与 `RiggingProvider` 能力。

---

## 4. 建议技术栈

### 4.1 MVP 推荐组合

| 层级 | 推荐 | 理由 |
|---|---|---|
| 核心语言 | Python 3.11+ | LLM/资产 API、GLB 处理、测试生态成熟 |
| 依赖管理 | uv 或 Poetry | uv 更快；Poetry 更传统。建议优先 uv，若团队熟悉 Poetry 可保留 |
| LLM Provider | LiteLLM SDK | 直接复用多 LLM 适配、DeepSeek、streaming、fallback 基础 |
| LLM 高性能网关 | 暂不内置，预留 Bifrost/LiteLLM Proxy 适配 | MVP 避免 sidecar 复杂度 |
| Asset Provider | Bridle 自研抽象 + httpx | 资产 API 缺少统一标准，需要领域建模 |
| HTTP 客户端 | httpx | async、stream、timeout、retry 配合好 |
| 配置 | TOML + Pydantic Settings | Python 原生友好，类型校验清晰 |
| Key 管理 P0 | 环境变量 + 脱敏展示 | 快速、安全、易测试 |
| Key 管理 P1 | keyring + 本地加密配置 | 桌面 BYOK 体验提升 |
| 缓存 P0 | diskcache 或 SQLite + 内容哈希 | 本地优先，零服务依赖 |
| 任务状态 | SQLite | 长任务、恢复、审计日志需要持久化 |
| 异步任务编排 | asyncio + bounded queue + worker pool | 防止 Meshy/Godot CLI/下载/GLB 处理阻塞桌面 UI |
| 日志 | structlog | 结构化、脱敏、后续接 OpenTelemetry |
| 可观测 P1 | OpenTelemetry SDK | 与 Harness 对标目标一致 |
| GLB 处理 | trimesh + pygltflib + Godot CLI | Python 检测，Godot CLI 做最终导入校验 |
| UI P0 | Tauri v2 + Python sidecar 或 Python 原生桌面 | 桌面软件是主要产品形态，MVP 直接围绕桌面体验设计 |
| CLI | Typer / argparse 薄接口 | 仅用于测试、自动化、调试和未来 CI，不作为主要用户入口 |
| 测试 | pytest + respx + vcr.py | mock API、录制真实 API、契约测试 |

### 4.2 为什么不是直接用 LangChain 做核心

LangChain 很适合 LLM 应用和 agent，但 Bridle 的中心不是聊天 agent，而是：

- 长耗时资产生成任务；
- 大文件下载；
- Godot 项目文件写入；
- 资产导入/修复；
- BYOK 桌面体验；
- 工作流模板和 Provider capability 匹配。

因此 LangChain 可以作为参考或局部集成，不建议成为核心架构中心。

### 4.3 为什么 LiteLLM 更适合 MVP

- DeepSeek 已支持；
- Python SDK 可嵌入，不必运行额外服务；
- 后续可切 Proxy；
- 支持较多 Provider，符合“尽量多供应商兼容”；
- 错误映射、streaming、fallback 等能力可直接利用。

Bridle 仍需包一层自己的 `LLMProviderFacade`，原因是：

- UI 需要统一事件；
- BYOK 需要统一配置和脱敏；
- 工作流需要 capability 查询；
- DeepSeek reasoner 的 `reasoning_content` 等特殊字段需要保留；
- 未来可能切换 Bifrost 或 OpenRouter，不希望业务层绑定 LiteLLM。

---

## 5. 架构建议

### 5.1 分层

```
Bridle Workflow Templates
        |
Bridle Domain Harness
        |-- Provider Capability Registry
        |-- BYOK Config / Key Resolver
        |-- Async Task Orchestrator
        |-- Event Bus / Progress Stream
        |-- Cache / Job Store
        |-- Error Taxonomy
        |
Provider Facades
        |-- LLMProviderFacade -> LiteLLM SDK / LiteLLM Proxy / Bifrost / direct OpenAI-compatible
        |-- Model3DProvider -> Meshy / Tripo / Hunyuan3D / fal.ai
        |-- TextureProvider -> Meshy / Polycam / ArmorLab / future
        |-- RiggingProvider -> Meshy / future
        |-- AnimationProvider -> DeepMotion / Plask / Cascadeur / future
        |
Godot Integration
        |-- FS Bridge
        |-- Godot CLI Bridge
        |-- MCP Client
        |-- Import / Repair Engine
```

### 5.2 LLM Provider 策略

MVP：

- `LLMProviderFacade` 调 LiteLLM SDK；
- 默认 Provider：DeepSeek；
- 默认模型：`deepseek/deepseek-chat`；
- reasoner 模型作为可选：`deepseek/deepseek-reasoner`；
- 支持 streaming；
- 保留 reasoning metadata；
- 对外输出 Bridle 自己的 `LLMEvent`。

Phase 2：

- 增加 LiteLLM Proxy 模式；
- 增加 Bifrost Gateway 模式；
- 增加 Provider fallback chain；
- 增加成本/额度统计；
- 增加 OpenTelemetry tracing。

### 5.3 资产 Provider 策略

MVP：

- `AssetJob` 统一任务状态：`created`、`queued`、`running`、`waiting_provider`、`downloading`、`importing`、`succeeded`、`failed`、`cancel_requested`、`cancelled`、`retrying`；
- `GeneratedAsset` 统一输出：文件 URL、本地路径、格式、贴图通道、license/usage metadata；
- Meshy 实现 `Model3DProvider`，可选实现 `TextureProvider` 和 `RiggingProvider`；
- 先支持 Text-to-3D preview/refine + GLB 下载。
- 所有 Meshy 任务、轮询、下载、GLB 检测和 Godot CLI 导入必须通过 Async Task Orchestrator 后台执行，桌面 UI 只订阅事件。

Phase 2：

- Tripo 实现第二个 `Model3DProvider`；
- fal.ai/Hunyuan3D 实现聚合型 Provider；
- DeepMotion 实现 `AnimationProvider`。

---

## 6. 待讨论决策

### 决策 1：LLM 层默认用 LiteLLM SDK 还是直接接 DeepSeek OpenAI-compatible API？

建议：LiteLLM SDK。

理由：

- 不自造多 LLM 轮子；
- 直接覆盖后续 OpenAI、Claude、Gemini、Ollama、OpenRouter 等；
- DeepSeek 已有支持；
- 与未来 fallback/budget/cost tracking 方向一致。

### 决策 2：是否内置 LiteLLM Proxy 或 Bifrost？

建议：MVP 不内置，只预留配置。

理由：

- 桌面 sidecar 会增加打包复杂度；
- MVP 用户大多是本地单用户；
- 真正瓶颈在资产生成 API 和导入管线；
- 后续性能模式再引入 Bifrost。

### 决策 3：桌面 UI 选 Tauri，还是 Python 原生桌面框架？

建议：优先评估 Tauri v2 + Python sidecar；备选为 PySide6。

理由：

- 用户明确希望 Bridle 是桌面软件；
- BYOK、项目选择、进度、日志、资产预览和设置更适合桌面交互；
- Tauri 便于做现代桌面 UI，体积比 Electron 更可控；
- Python sidecar 保留现有 AI/资产处理生态；
- CLI 只作为薄接口服务自动化、调试和未来 CI。

需要避免：

- 不把 local Web UI 作为 MVP 主路线；
- 不把 CLI 当作主要产品体验；
- 不引入完整 Web 后端形态，除非只是桌面壳内部通信机制。

### 决策 4：配置格式用什么？

建议：TOML。

理由：

- Python 3.11 有 `tomllib`；
- 适合项目级配置；
- 比 YAML 少隐式类型坑；
- 可与 `pyproject.toml` 生态统一。

### 决策 5：Bridle 是否要支持“外部 LLM Gateway URL”？

建议：必须支持。

理由：

- 用户可能已有 LiteLLM、Bifrost、OpenRouter、Portkey；
- BYOK 高级用户会希望使用自己的网关；
- 有利于企业版和团队用量控制。

---

## 7. 当前推荐结论

建议采用：

> Python 3.11+ 核心 + LiteLLM SDK 做 LLM Provider 基础 + Bridle 自研资产 Provider/Harness 领域层 + Meshy 首个资产 Provider + 桌面应用优先 + CLI 薄接口辅助。

技术路线口号：

> LLM Provider 不造轮子，游戏资产 Harness 自己做深。

---

## 8. 是否从先进 Harness 项目开始

结论：可以，而且应该。但 Bridle 不能直接成为 LangChain/Dify/Haystack 的换皮应用，而应采用“组合式借鉴 + 领域内核自研”的策略。

Bridle 的本质是：

> 面向游戏开发的垂直 Harness：把 LLM、3D/纹理/动画生成 API、Godot 项目上下文、资产导入修复、工作流模板、BYOK 和可观测性整合成一个可生产使用的本地工具。

因此可以把先进 Harness 拆成几个能力来源：

| 能力 | 可参考项目 | Bridle 采用方式 |
|---|---|---|
| 多 LLM Provider | LiteLLM、Bifrost、Portkey | MVP 用 LiteLLM SDK；预留 Bifrost/Portkey/OpenRouter 外部 Gateway |
| 类型安全和结构化输出 | Pydantic AI | 采用 Pydantic 模型定义工作流输入、Provider 输出、LLM 结构化结果 |
| 管线式工作流 | Haystack | 借鉴 component/pipeline 思想，但工作流状态机自研以适配长耗时资产任务 |
| Agent/工具调用 | LangGraph、Semantic Kernel、Haystack Agent | MVP 不做多 Agent；只保留工具调用和可恢复步骤设计 |
| Prompt/任务优化 | DSPy | Phase 2+ 用于优化“项目上下文 → GDScript/导入脚本”的提示和评测 |
| 高性能网关 | Bifrost | 作为性能目标和可选 LLM Gateway，不作为 MVP 默认 sidecar |
| BYOK/路由/guardrails | Portkey、LiteLLM Proxy | 借鉴配置、脱敏、fallback、budget、guardrails，但本地 UX 自研 |

### 8.1 不建议的路线

不建议直接从一个通用 Harness fork 开始改，因为：

- 通用 Harness 的核心假设通常是聊天、RAG、Agent 或企业 API 网关；
- Bridle 的核心复杂度在游戏资产长任务、文件下载、GLB/材质/骨骼导入、Godot 项目写入；
- 直接 fork 会继承大量无关抽象，后续桌面分发和本地优先体验会被拖住；
- 资产 Provider 生态没有统一标准，最终仍要自研领域模型。

### 8.2 建议的起步方式

建议从一个“薄内核 + 可替换后端”的架构起步：

```
Bridle Core
  - typed domain models
  - workflow/job state machine
  - event stream
  - BYOK config and key resolver
  - provider capability registry
  - Godot import pipeline
  - desktop-facing application service API

External/Embedded Harness Modules
  - LiteLLM SDK for LLM providers
  - optional LiteLLM Proxy / Bifrost / OpenRouter gateway
  - Pydantic models for structured IO
  - OpenTelemetry-compatible event schema
```

也就是说，Bridle 从先进 Harness 的“模块”和“模式”开始，而不是从某一个平台的完整代码库开始。

### 8.3 可执行的技术路线

MVP 选择：

1. **LiteLLM SDK**：接 DeepSeek 和未来 LLM，不自研 LLM Provider。
2. **Pydantic v2**：所有请求、响应、事件、配置、资产元数据都用类型模型。
3. **Bridle Workflow Engine**：自研轻量状态机，专门处理资产生成这种长任务。
4. **Async Task Orchestrator**：`asyncio` + 有界队列 + worker pool；所有长任务后台执行，Tauri 命令只提交 job/查询状态/订阅事件。
5. **Bridle Provider Facade**：LLM facade 调 LiteLLM；Asset facade 调 Meshy/Tripo/fal/DeepMotion。
6. **OpenTelemetry-ready events**：先记录结构化事件，后续直接接 tracing。
7. **Benchmark harness**：从第一版就记录延迟、重试、缓存、下载、导入耗时。
8. **Desktop-first shell**：桌面应用承载项目选择、BYOK、工作流执行、进度、日志和资产结果；CLI 只暴露同一 application service 的薄接口。

Phase 2 选择：

1. 引入 LiteLLM Proxy 或 Bifrost 作为可选外部网关；
2. 用 Haystack/Pydantic AI 的 pipeline/agent 思路增强模板编排；
3. 用 DSPy 做 Prompt/上下文注入优化；
4. 增加 guardrails、budget、fallback、provider health dashboard。

### 8.4 初始代码骨架建议

如果正式进入概要设计，建议 Bridle Core 先按这些包组织：

```
bridle/
  domain/
    llm.py
    assets.py
    events.py
    jobs.py
    capabilities.py
  harness/
    workflow.py
    task_orchestrator.py
    workers.py
    event_bus.py
    cache.py
    benchmark.py
    errors.py
  providers/
    llm_litellm.py
    asset_meshy.py
    base.py
  config/
    settings.py
    keyring.py
  godot/
    project.py
    import_pipeline.py
    cli.py
  app/
    services.py
    desktop_api.py
```

这会让 Bridle 一开始就有 Harness 的样子，但不会被通用 Agent 框架喧宾夺主。

---

## 9. 参考链接

- LiteLLM Docs: https://docs.litellm.ai/
- LiteLLM DeepSeek Provider: https://docs.litellm.ai/docs/providers/deepseek
- Bifrost GitHub: https://github.com/maximhq/bifrost
- Portkey Gateway GitHub: https://github.com/Portkey-AI/gateway
- LangChain DeepSeek: https://docs.langchain.com/oss/python/integrations/chat/deepseek
- Pydantic AI: https://pydantic.dev/docs/ai/overview/
- Haystack Docs: https://docs.haystack.deepset.ai/docs/intro
- Semantic Kernel GitHub: https://github.com/microsoft/semantic-kernel
- DSPy GitHub: https://github.com/stanfordnlp/dspy
- Meshy Text-to-3D API: https://docs.meshy.ai/en/api/text-to-3d
- Tripo API Docs: https://platform.tripo3d.ai/
- fal Hunyuan3D: https://fal.ai/models/fal-ai/hunyuan3d/v2
- DeepMotion Animate 3D API: https://www.deepmotion.com/animate-3d-api
- DeepMotion REST API GitHub: https://github.com/DeepMotion/Animate-3D-REST-API
