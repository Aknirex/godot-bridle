# godot-bridle 需求分析

> **文档版本**：v0.2
> **创建日期**：2026-06-18
> **输入文档**：
> - [00-initial-need-and-situation.md](00-initial-need-and-situation.md) v0.2
> - [01-engineering-plan.md](01-engineering-plan.md) v0.1
> **阶段**：需求分析
> **状态**：待评审

---

## 1. 需求结论摘要

Bridle 的核心需求可以收敛为一句话：

> 为 Godot 开发者提供一个本地优先、供应商可替换的 AI 资产与代码辅助 Harness，把外部 AI 生成结果稳定地转化为 Godot 项目中可用、可维护的资产和上下文。

从需求分析角度看，项目的真正壁垒不是“调用某个 AI API”，而是以下三件事的组合：

1. **Provider 抽象与可替换性**：LLM 和资产生成服务必须被统一接口隔离，避免工作流绑定具体厂商。
2. **Godot 项目上下文理解**：系统必须理解目标项目的 Godot 版本、插件、目录结构和已有资源，降低 AI 输出不可用代码的概率。
3. **资产落地管线**：AI 生成的模型、纹理、绑定结果必须能被检测、修复、导入，并在 Godot 中形成可引用资源。
4. **BYOK 与多供应商兼容体验**：用户应能低成本接入、测试、切换尽量多的 LLM 和游戏资产生成 API，Bridle 不应把用户锁进任何默认供应商。
5. **高性能 Harness 基础设施**：Bridle 可以基于或借鉴开源先进 Harness，但最终需要在 Godot 资产生产场景中达到高于主流产品平均水平的吞吐、延迟、稳定性和可观测性。

MVP 应优先证明“从自然语言到 Godot 可用资产”的闭环，而不是一次性实现完整 Harness 平台。产品形态必须以桌面软件为主，避免把本地 Web UI 作为主要体验。建议将 v0.1 的验收重心放在：

- 一个可运行的桌面应用原型；
- DeepSeek 作为测试阶段优先 LLM Provider，同时保留 OpenAI/Claude 兼容路径；
- Meshy 作为首个 Asset Provider；
- 一个最小但真实的角色生成工作流；
- 对 Godot 项目进行元数据采集和资产写入；
- BYOK 配置体验可用，至少覆盖环境变量、配置校验、Key 脱敏展示和连接测试；
- 对 GLB 做基础检查、导入和材质映射，复杂修复以明确错误提示或 Godot/Blender 手动指南兜底。

---

## 2. 目标用户与使用场景

### 2.1 主要用户

**Godot 独立开发者**

- 需要快速获得可用于原型或小型项目的 3D 角色/道具/场景资产。
- 具备基本 Godot 使用能力，但不希望反复在 AI 平台、Blender、Godot 导入器之间手动搬运。
- 关心成本、可控性和供应商切换能力。

**Godot 技术美术 / 资产管线开发者**

- 关注批量导入、材质映射、命名规范、碰撞体和资源组织。
- 可能贡献 Provider 适配器或工作流模板。

**开源贡献者 / 模板作者**

- 需要稳定的插件式接口来新增 Provider、模板和导入规则。
- 关心贡献门槛、测试方式和文档清晰度。

### 2.2 核心场景

**场景 A：生成并导入一个角色**

用户选择 Godot 项目，输入角色描述，Bridle 调用资产生成 Provider，下载 GLB/纹理/绑定结果，执行基础检查和导入，生成 Godot 资源、场景节点和样板引用脚本。

**场景 B：让 LLM 根据项目上下文生成代码**

用户请求生成或修改 GDScript。Bridle 采集 Godot 版本、插件、文件结构和已有资源摘要，将其注入 Prompt，使 LLM 输出更贴合当前项目。

**场景 C：切换 Provider**

用户从配置中切换 LLM 或资产 Provider。工作流模板不改代码，只依赖统一接口执行。

**场景 D：配置 BYOK 并测试供应商连接**

用户在 Bridle 中配置 DeepSeek、OpenAI、Claude、Meshy 等供应商的 API Key。系统能检查 Key 来源、验证连接、展示脱敏状态、提示缺失能力，并允许用户为不同任务设置默认 Provider。

**场景 E：贡献新 Provider 或模板**

贡献者实现 `BaseLLMProvider` / `BaseAssetProvider` 或新增模板定义，并通过契约测试验证兼容性。

---

## 3. 业务目标

### 3.1 MVP 业务目标

1. 验证 Godot 用户确实需要“AI 生成资产到可用 Godot 资源”的自动化管线。
2. 验证 Provider 抽象可以支撑供应商切换，而不是停留在概念层。
3. 形成一个可演示、可下载、可贡献的开源项目骨架。
4. 建立 Bridle 与单一 Meshy/Godot 插件的差异：Bridle 是 Harness 和管线，不是单 Provider 外壳。
5. 验证 DeepSeek API 能作为测试阶段 LLM Provider 接入，并沉淀可复用的 OpenAI-compatible Provider 适配模式。
6. 建立 Harness 性能基线，为后续对标 LangChain、LlamaIndex、Dify、Flowise、Mirascope 等主流项目提供可量化依据。

### 3.2 非目标

1. MVP 不追求生成完整游戏。
2. MVP 不追求一次性覆盖所有资产类型和 Provider，但架构必须把“尽量多供应商兼容”作为刚性约束。
3. MVP 不承担云端 API 成本，不提供 SaaS 后端。
4. MVP 不承诺自动修复所有 GLB 质量问题。
5. MVP 不实现完整模板市场、企业协作或多 Agent 编排。

---

## 4. 需求分层

### 4.1 P0：MVP 必须满足

| 编号 | 需求 | 验收要点 |
|---|---|---|
| RA-P0-01 | 能打开或选择一个 Godot 4.6+ 项目 | 能识别 `project.godot`，记录项目路径 |
| RA-P0-02 | 能采集项目元数据 | 至少包括 Godot 版本、插件列表、目录结构摘要 |
| RA-P0-03 | 定义统一 Provider 接口 | `BaseLLMProvider`、`BaseAssetProvider` 有清晰方法、数据结构和契约测试 |
| RA-P0-04 | 支持 DeepSeek LLM Provider | 测试阶段优先使用 DeepSeek API，能完成普通响应和流式响应 |
| RA-P0-05 | 支持 Meshy 资产生成 Provider | 至少完成 Text-to-3D 到资产下载的闭环 |
| RA-P0-06 | 支持基础 BYOK 配置体验 | 支持环境变量读取、Key 缺失提示、脱敏展示、连接测试，不把密钥写入仓库或项目文件 |
| RA-P0-07 | 能把生成资产写入 Godot 项目 | 输出到约定目录，生成或更新必要资源文件 |
| RA-P0-08 | 能处理 GLB 基础导入 | 检查文件存在、格式、比例、材质贴图路径，能生成 Godot 可识别资源 |
| RA-P0-09 | 有角色生成工作流模板 | 用户输入 prompt 后能执行一条端到端流程 |
| RA-P0-10 | 有基础错误提示和日志 | API 失败、Key 缺失、项目无效、导入失败时可诊断 |
| RA-P0-11 | 有最小桌面用户界面 | 用户无需写 Python 代码或命令即可执行核心流程；CLI 只作为接口和调试入口 |
| RA-P0-12 | 有测试覆盖核心接口 | Provider 契约、配置读取、元数据采集、导入路径生成有单元测试 |
| RA-P0-13 | 建立 Harness 性能基线 | 记录 LLM 首 token 延迟、总响应耗时、缓存命中耗时、Provider 切换耗时、资产任务状态轮询开销 |
| RA-P0-14 | Provider 能力模型可扩展 | LLM、3D 模型、纹理、动画、绑定等能力以 capability 声明，不以硬编码供应商分支实现 |
| RA-P0-15 | 异步任务编排引擎 | Meshy 生成、资产下载、GLB 检测、Godot CLI 导入等长任务必须后台执行，不阻塞桌面 UI |

### 4.2 P1：MVP 可延后但应预留设计

| 编号 | 需求 | 说明 |
|---|---|---|
| RA-P1-01 | OpenAI/Claude 兼容 Provider | 用于证明接口可替换性，并复用 DeepSeek 沉淀出的 OpenAI-compatible 适配层 |
| RA-P1-02 | Image-to-3D、Retexture、Auto-Rigging | 可在 Meshy Text-to-3D 闭环稳定后扩展 |
| RA-P1-03 | 完整 BYOK Key 管理 | 加密存储、Provider 级配置、项目级覆盖、连接测试、额度/限流提示 |
| RA-P1-04 | Provider 回退链 | 接口设计预留，功能可 Phase 2 |
| RA-P1-05 | OpenTelemetry | 日志结构先设计兼容，完整 tracing 后置 |
| RA-P1-06 | 桌面应用完整体验 | 桌面应用是主要产品形态；补齐项目管理、BYOK、进度、日志、资产预览和设置体验 |
| RA-P1-07 | Godot Asset Store 打包 | 需在可运行版本稳定后执行 |
| RA-P1-08 | Harness 对标评测 | 与主流开源 Harness 在流式延迟、缓存、Provider 回退、错误恢复、可观测性维度做基准对比 |
| RA-P1-09 | 资产 Provider 插件化加载 | 第三方 Provider 可通过独立包或插件目录注册，不需要改 Bridle 核心代码 |

### 4.3 P2：长期能力

| 编号 | 需求 | 说明 |
|---|---|---|
| RA-P2-01 | 多资产 Provider 覆盖 | Tripo、Hunyuan3D、Polycam、DeepMotion、Plask、Cascadeur 等 |
| RA-P2-02 | 模板市场 | 依赖模板规范和用户规模 |
| RA-P2-03 | 配额与成本仪表盘 | 需要多 Provider 用量数据沉淀 |
| RA-P2-04 | 企业协作和私有部署 | 不应进入 MVP 路线 |
| RA-P2-05 | CI/命令行自动化模式 | 对专业团队有价值，可作为 v1.0+ 能力 |

---

## 5. 功能需求分析

### 5.1 项目管理

Bridle 需要维护“当前 Godot 项目”的概念。项目管理的最小需求包括：

- 选择项目目录；
- 校验 `project.godot` 存在；
- 保存最近打开项目；
- 为后续元数据采集、资产写入、脚本生成提供项目根路径。

待明确：

- 是否允许同时打开多个 Godot 项目；
- Bridle 配置是用户级、项目级，还是两者都有；
- 生成资产默认写入路径，例如 `res://bridle/generated/` 是否固定。

### 5.2 元数据采集与上下文桥

元数据采集是 LLM 代码质量的基础。MVP 不需要完整理解整个项目，但需要稳定输出结构化摘要。

最小元数据：

- Godot 项目路径；
- Godot 版本，优先从可用 CLI 或项目配置推断；
- 插件列表，例如 `addons/` 与 `project.godot` 中启用状态；
- 关键目录结构；
- `.gd`、`.tscn`、`.tres` 文件数量和代表性路径；
- 已生成资产索引。

上下文桥需要把元数据转为 Prompt 可用内容，并控制长度，避免把完整项目塞给 LLM。

### 5.3 Provider 抽象

Provider 抽象应先定义数据模型，再定义行为。该抽象是 Bridle 的核心产品能力，不只是代码整理手段。MVP 必须避免出现“工作流知道具体供应商字段”的设计。

建议 MVP 明确以下对象：

- `ProviderCapabilities`：声明 Provider 支持文本生成、流式响应、Text-to-3D、Image-to-3D、Retexture、Rigging 等能力；
- `LLMRequest` / `LLMResponse` / `LLMStreamChunk`；
- `AssetGenerationRequest` / `AssetGenerationJob` / `GeneratedAsset`；
- `ProviderError` 分类：认证失败、限流、网络错误、供应商任务失败、能力不支持。

关键验收点：

- 工作流只依赖抽象接口，不直接 import 具体 Provider；
- Provider 能力不足时返回明确错误，而不是运行时崩溃；
- API Key 读取由 Key Manager 统一处理。

Provider 类型至少分为：

- `LLMProvider`：文本生成、代码生成、流式响应、结构化输出、embedding；
- `Model3DProvider`：Text-to-3D、Image-to-3D、模型格式导出；
- `TextureProvider`：Retexture、PBR 材质生成、贴图通道导出；
- `AnimationProvider`：动作生成、动作捕捉、动画片段导出；
- `RiggingProvider`：自动绑定、骨骼规范、蒙皮结果导出。

同一供应商可以实现多个能力，但系统不能假设某个供应商一定覆盖完整链路。

### 5.4 LLM 能力

MVP 的 LLM 需求应聚焦在：

- DeepSeek API 作为测试阶段优先接入对象；
- 根据上下文生成 GDScript 或资源引用样板；
- 支持流式输出；
- 支持缓存或至少可缓存的请求签名；
- 能在无 Key、Key 错误、限流时给出清晰提示。

DeepSeek 接入的需求定位：

- 作为 MVP 测试阶段默认 LLM Provider；
- 如果 API 兼容 OpenAI Chat Completions 风格，应抽象出通用 `OpenAICompatibleLLMProvider`，DeepSeek 作为其配置实例或轻量子类；
- Provider 配置必须支持 `base_url`、`model`、`api_key_env`、timeout、max retries；
- 测试用例应覆盖非流式、流式、认证失败、限流/重试和错误消息映射。

语义缓存在 MVP 中风险偏高。建议拆为两层：

1. **P0 内容哈希缓存**：对相同 Prompt、模型、参数命中缓存。
2. **P1 语义缓存**：基于 embedding 相似度，待核心闭环稳定后实现。

### 5.5 资产生成

MVP 应以 Meshy 的 Text-to-3D 作为首条闭环，原因是覆盖度高且能快速证明价值。但需求上必须把 3D 模型、纹理、动画、绑定拆成独立能力，不把 Meshy 的产品边界当成 Bridle 的系统边界。

最小流程：

1. 提交生成请求；
2. 轮询或接收任务状态；
3. 下载 GLB 和相关纹理；
4. 写入 Godot 项目目录；
5. 记录资产元数据；
6. 交给导入引擎处理。

需要在需求中明确：

- 生成任务可能耗时数分钟，桌面 UI 必须展示进度；CLI 仅作为接口输出机器可读状态；
- 外部 API 失败属于常态，需要可恢复；
- 资产质量不稳定，Bridle 只承诺做可检测、可修复范围内的处理。
- 不同资产 Provider 的任务模型可能不同，包括同步返回、异步 job、Webhook、轮询、文件 URL、对象存储下载等，适配层必须统一成 Bridle 内部任务状态模型。
- 所有资产生成、下载、导入和 Godot CLI 操作都必须通过异步任务编排引擎执行，桌面 UI 只能提交 job、订阅事件、查询状态和请求取消。

### 5.6 BYOK 体验

BYOK 是 Bridle 的核心需求，不是附属配置项。用户需要相信 Bridle 不托管、不上传、不泄露密钥，同时又能方便地知道某个 Provider 是否配置成功。

MVP 基础体验：

- 支持从环境变量读取 Key；
- 支持 Provider 级配置 `api_key_env`、`base_url`、`model`、默认任务类型；
- 桌面 UI 和 CLI 中只展示脱敏 Key，例如 `sk-...abcd`；
- 提供连接测试，区分认证失败、网络失败、模型不存在、能力不支持；
- 日志默认脱敏，不记录 Authorization header、完整 Key 或带签名下载 URL；
- 支持按任务类型设置默认 Provider，例如代码生成用 DeepSeek，3D 生成用 Meshy。

P1 完整体验：

- 系统钥匙串或本地加密存储；
- 用户级默认配置和项目级覆盖配置；
- 多 Key 轮换；
- Provider 额度、限流、余额或用量提示；
- 连接健康状态和最近错误记录；
- 导入/导出配置时默认排除密钥。

### 5.7 GLB 导入与修复

这是项目风险最高的核心模块。需求应避免承诺“万能修复”，改为分级处理：

**P0 必做**

- 检查 GLB 文件存在且可解析；
- 统一输出目录和命名；
- 检查基础尺寸并提供缩放建议或自动 scale；
- 提取或关联 PBR 贴图；
- 生成 Godot 可识别的材质资源；
- 生成引用脚本或示例场景。

**P1 增强**

- 常见法线反向检测与修复；
- UV 缺失或异常检测；
- 碰撞体自动生成策略；
- Godot CLI 导入后校验。

**需要明确不可保证**

- 不保证修复拓扑损坏模型；
- 不保证所有绑定骨骼满足游戏动画需求；
- 不保证所有第三方生成器输出格式一致。

### 5.8 工作流模板

角色生成模板是 MVP 的产品化入口。它至少包含：

- 输入参数：角色描述、风格、目标目录、是否生成样板脚本；
- Provider 选择：默认 Meshy，可通过能力声明适配未来 Provider；
- 步骤定义：生成、下载、导入、材质、碰撞体、脚本；
- 失败策略：可重试、跳过、回滚生成文件或保留中间产物。

模板格式需要在需求阶段先确定方向：

- 配置文件描述流程；
- Python 脚本实现复杂步骤；
- 模板元数据包含名称、描述、输入 schema、所需能力和输出资源。

### 5.9 Harness 基础设施与性能目标

Bridle 可以基于开源先进 Harness 构建，或借鉴其架构模式，但不能只停留在“能调用 Provider”。Harness 层必须服务于游戏资产生产的特点：长任务、异步轮询、大文件下载、上下文注入、可恢复失败和本地缓存。

异步任务编排引擎是 Harness 层的 P0 组件。它必须提供：

- `submit_job()`：桌面 UI 提交任务后立即返回 `job_id`；
- `get_job_status()`：查询当前状态、阶段、进度、错误；
- `stream_job_events()`：订阅进度、日志、Provider 轮询、下载、Godot CLI 导入等事件；
- `cancel_job()`：请求取消尚未完成的任务；
- SQLite job store：持久化任务状态和阶段边界；
- worker pool：执行 Provider 调用、下载、GLB 检测、Godot CLI 等长任务；
- timeout/retry/cancellation：所有外部调用必须有超时、重试和取消检查。

桌面 UI 不允许直接同步等待 Meshy、DeepSeek、Godot CLI 或大文件处理完成。

需要重点借鉴或对标的能力：

- LangChain / LlamaIndex：Provider 抽象、工具调用、缓存、回调事件；
- Mirascope：类型安全、轻量 Provider 封装；
- Dify / Flowise：可视化工作流、运行日志、用户配置体验；
- LiteLLM：多 LLM Provider 统一调用、OpenAI-compatible 适配、成本/限流抽象；
- Haystack / Semantic Kernel：管线化和可组合组件。

Bridle 的 Harness 性能目标：

- 流式 LLM 首 token 延迟开销应尽量接近底层 Provider 原始调用，不因 Harness 包装引入明显阻塞；
- Provider 选择、能力匹配和 Key 解析应为轻量本地操作；
- 缓存命中路径应绕过外部 API，并返回明确的 cache metadata；
- 资产下载、哈希、导入处理应支持进度事件；
- 长任务应支持恢复、重试和幂等输出目录；
- 所有 Provider 调用应产生统一事件，便于 UI、日志、测试和未来 tracing 复用。
- Tauri command 必须保持短生命周期，只负责提交任务、查询状态或订阅事件，不能承载长时间阻塞业务。

对标指标建议：

| 指标 | MVP 基线 | 后续目标 |
|---|---|---|
| LLM 首 token Harness 额外开销 | 可记录 | 低于主流开源 Harness 平均值 |
| 精确缓存命中耗时 | 可记录 | 本地毫秒级返回 |
| Provider 切换耗时 | 可记录 | 不需要重启应用 |
| API 错误分类准确率 | 人工验证 | 常见错误均映射到统一错误类型 |
| 资产任务恢复能力 | 基础 job 状态记录 | 支持失败后从下载/导入阶段恢复 |
| Provider 新增成本 | 契约测试覆盖 | 普通 Provider 不改核心代码 |

---

## 6. 非功能需求

| 类别 | 需求 | MVP 建议 |
|---|---|---|
| 可用性 | 用户能在 5-10 分钟内完成首次配置和生成 | README + 示例项目 + 明确错误提示 |
| 性能 | 端到端角色生成目标 < 5 分钟 | 受外部 API 影响，需拆分内部耗时和 Provider 耗时 |
| Harness 性能 | Provider 抽象层不能显著拖慢底层 API | 建立基准测试，记录首 token、缓存命中、Provider 切换、任务轮询开销 |
| 可靠性 | 外部 API 失败不应破坏 Godot 项目 | 所有写入集中到生成目录，失败保留日志 |
| 响应性 | 长任务不能阻塞桌面 UI | Provider、下载、GLB、Godot CLI 均后台 job 化，UI 通过事件更新 |
| 安全性 | API Key 不进入日志和仓库 | BYOK 优先，环境变量起步，日志脱敏，P1 加密存储 |
| 可维护性 | Provider 新增成本低 | 抽象接口、能力声明、契约测试 |
| 可测试性 | 核心逻辑不依赖真实 API | mock Provider + vcr.py 录制回放 |
| 可观测性 | 问题可诊断 | MVP 结构化日志，Phase 2 tracing |
| 跨平台 | 面向 Windows/macOS/Linux | 路径处理必须使用跨平台 API |
| 本地优先 | 除外部 AI API 外不依赖云服务 | 配置、缓存、日志本地存储 |

---

## 7. 关键约束

1. **Godot 版本约束**：文档目标为 Godot 4.6+。如果需要兼容 4.4/4.5，需单独声明。
2. **外部 API 约束**：DeepSeek、Meshy、OpenAI、Anthropic 等 API 行为、价格、限流和返回格式可能变化。
3. **资产质量约束**：AI 生成资产的几何、UV、材质和骨骼质量不可完全控制。
4. **桌面框架约束**：Tauri + Python sidecar 会引入前后端通信、打包和跨平台复杂度。
5. **MCP 约束**：Godot MCP 生态已有多个实现，但是否内置、复用、还是适配其中一个，需要设计阶段确认。
6. **开源维护约束**：MVP 人力为 1-2 人，需求必须控制范围。

---

## 8. 风险与需求调整建议

| 风险 | 表现 | 建议 |
|---|---|---|
| MVP 范围过大 | 桌面 UI、完整 Meshy 能力、语义缓存、GLB 修复同时推进 | 先做可演示闭环，再扩能力 |
| GLB 修复承诺过强 | 用户期望任意模型都能一键修好 | 把修复能力拆成“检测、自动修复、人工建议”三级 |
| 语义缓存复杂度高 | embedding、相似度阈值、误命中会带来新问题 | MVP 先做精确缓存和资产哈希缓存 |
| Provider 抽象过早复杂 | 为未来 Provider 设计太多接口但无人使用 | 用 Meshy + 一个 mock Provider 驱动接口演化 |
| Provider 抽象过窄 | 只适配 DeepSeek/Meshy，后续接入其他供应商时重构成本高 | 能力模型从一开始覆盖 LLM、3D、纹理、动画、绑定，不把供应商字段泄露到工作流 |
| BYOK 体验薄弱 | 用户配置失败、Key 泄露疑虑、切换困难 | 把连接测试、脱敏、错误分类、Provider 默认策略列为 MVP 验收 |
| Harness 性能目标空泛 | 只说“对标主流”，无法判断是否达到 | 建立基准指标和对照样例，持续记录首 token、缓存、轮询、下载、导入耗时 |
| 桌面 UI 被长任务阻塞 | Meshy 生成或 Godot CLI 导入期间界面无响应 | P0 引入异步任务编排引擎；Tauri 命令只提交 job 和订阅事件 |
| 桌面打包拖慢进度 | Tauri sidecar、签名、路径权限问题消耗周期 | 仍以桌面软件为 MVP 目标，但先保持 UI 功能克制，CLI 只服务测试和调试 |
| 竞品复制 Meshy 集成 | 单 Provider 功能容易被追平 | 差异化应落在抽象接口、模板规范和 Godot 导入管线 |

---

## 9. MVP 验收方案

建议将 v0.1-alpha 的验收定义为一条可重复演示路径：

1. 用户准备一个 Godot 4.6+ 空项目。
2. 用户配置 `DEEPSEEK_API_KEY` 和 `MESHY_API_KEY`。
3. 用户启动 Bridle，选择 Godot 项目目录。
4. Bridle 显示项目元数据摘要。
5. 用户选择“角色生成”模板，输入“low poly knight character”。
6. Bridle 调用 Meshy 生成并下载 GLB。
7. Bridle 将资产写入 `res://bridle/generated/<asset_id>/`。
8. Bridle 生成材质资源、示例场景或引用脚本。
9. 用户在 Godot 中刷新项目，能看到生成资产和示例资源。
10. 失败时，用户能从 UI/日志中知道失败发生在认证、生成、下载、导入还是写入阶段。

验收指标：

- 首次配置成功率可由内部测试记录；
- 端到端流程可在同一测试项目中重复运行；
- 所有生成文件集中在可清理目录；
- 无 API Key 泄露到日志；
- DeepSeek 连接测试可明确反馈成功、认证失败或网络失败；
- Provider 接口有自动化契约测试；
- Harness 基准日志能输出关键耗时指标；
- Meshy 生成、下载和 Godot CLI 导入期间桌面 UI 不冻结，进度事件可见；
- 用户能取消尚未完成的长任务，系统能记录取消状态；
- 至少一个真实 API 调用流程有录制回放测试。

---

## 10. 待确认问题

### 10.1 产品边界

1. MVP 桌面应用采用 Tauri + Python sidecar，还是 Python 原生桌面框架？
2. 首个公开版本面向“开发者预览”还是“普通 Godot 用户”？
3. 角色生成模板是否必须包含 Auto-Rigging，还是 Text-to-3D + 材质 + 示例脚本即可？
4. 是否需要支持已有模型的 Retexture 作为 MVP 第二条工作流？
5. 测试阶段 DeepSeek 是唯一默认 LLM，还是与 OpenAI/Claude 并列展示？

### 10.2 技术决策

1. Godot 版本检测优先使用 `godot --version`，还是仅解析项目文件？
2. Godot 通信的 MVP 顺序是 FS 优先、CLI 其次、MCP 后置，还是必须同时接入 MCP？
3. GLB 修复优先使用 Python 库，还是 Godot CLI 导入脚本？
4. 缓存 MVP 是否只做精确缓存和内容哈希缓存？
5. 配置文件格式选择 TOML、YAML 还是 JSON？
6. 是否采用或封装 LiteLLM 一类开源 Harness 作为多 LLM 适配基础，还是自研轻量 Provider 层？
7. 资产 Provider 插件加载机制采用 Python entry points、插件目录，还是配置注册？
8. Harness 性能对标的主流产品清单和测试场景如何固定？

### 10.3 运营与发布

1. Godot Asset Store 发布的是独立应用入口、Godot 辅助插件，还是模板包？
2. MIT 协议是否已最终确定？
3. 是否需要在 v0.1-alpha 前准备官网/文档站？

---

## 11. 建议的下一阶段输入

需求评审通过后，建议进入概要设计阶段，优先产出：

1. Provider 接口设计说明；
2. 资产生成与导入流程时序图；
3. 项目目录与配置规范；
4. MVP 技术选型决策记录；
5. BYOK 配置与密钥安全设计；
6. Harness 基准测试方案；
7. v0.1-alpha 里程碑任务拆解。
