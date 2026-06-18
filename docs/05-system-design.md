# godot-bridle 概要设计

> **文档版本**：v0.1
> **创建日期**：2026-06-18
> **阶段**：概要设计
> **依赖文档**：
> - [02-requirements-analysis.md](02-requirements-analysis.md) v0.2
> - [03-provider-research-and-tech-stack.md](03-provider-research-and-tech-stack.md) v0.1
> - [04-architecture-decisions.md](04-architecture-decisions.md) v0.1
> **状态**：待评审

---

## 1. 设计目标

Bridle MVP 的概要设计目标是完成一条稳定闭环：

> 桌面应用选择 Godot 项目 → 配置 BYOK → 提交角色生成 job → Meshy 生成并下载 GLB → Bridle 检测和导入 → Godot 项目出现可用资产和示例资源。

设计必须满足：

- 桌面优先，不走 WebUI 主路线；
- 所有长任务后台执行，不阻塞 Tauri UI；
- LLM Provider 复用 LiteLLM，测试阶段默认 DeepSeek；
- 资产 Provider 自研抽象，MVP 默认 Meshy；
- Provider 通过 capability 匹配，不让工作流绑定供应商；
- BYOK、安全脱敏、连接测试从 MVP 开始具备；
- Godot 集成 MVP 走 FS + Godot CLI，MCP 后置。

---

## 2. 系统分层

```
Desktop Layer
  Tauri v2 + TypeScript
  - project picker
  - BYOK settings
  - workflow launcher
  - job progress/log/result views

Application Service Layer
  bridle.app
  - desktop-facing API
  - submit/query/cancel jobs
  - provider connection tests
  - project metadata summary

Domain Harness Layer
  bridle.domain + bridle.harness
  - Pydantic domain models
  - async task orchestrator
  - workflow state machine
  - event bus
  - job store
  - cache
  - benchmark recorder
  - error taxonomy

Provider Layer
  bridle.providers
  - LLMProviderFacade -> LiteLLM SDK
  - AssetProviderFacade -> Meshy MVP
  - capability registry

Godot Integration Layer
  bridle.godot
  - project detector
  - metadata collector
  - import pipeline
  - Godot CLI bridge
```

---

## 3. 进程与通信边界

### 3.1 MVP 进程模型

```
┌──────────────────────┐
│ Tauri Desktop Process │
│ UI + Tauri Commands   │
└───────────┬──────────┘
            │ command/event bridge
┌───────────▼──────────┐
│ Python Sidecar        │
│ Bridle Core           │
│ asyncio event loop    │
│ bounded job queue     │
│ worker pool           │
└───────────┬──────────┘
            │
┌───────────▼──────────┐
│ External Processes    │
│ Godot CLI/headless    │
└──────────────────────┘
```

### 3.2 通信原则

- Tauri command 只能做短生命周期操作。
- 桌面提交长任务时调用 `submit_job()`，立即拿到 `job_id`。
- 桌面通过事件订阅或轮询查询 job 状态。
- Python sidecar 内部负责 Provider 请求、轮询、下载、Godot CLI 和文件写入。
- CLI 与桌面复用同一 `bridle.app.services`，不能另写业务路径。

---

## 4. 核心模块设计

### 4.1 `bridle.app`

职责：

- 向桌面层暴露稳定 API；
- 封装异步任务提交、查询、取消；
- 提供项目打开、Provider 配置、连接测试；
- 聚合 domain/harness/provider/godot 层，不把底层细节泄露给 UI。

核心接口草案：

```python
class BridleAppService:
    async def open_project(self, path: Path) -> ProjectSummary: ...
    async def list_providers(self) -> list[ProviderSummary]: ...
    async def test_provider(self, provider_id: str) -> ProviderHealth: ...
    async def submit_workflow(self, request: WorkflowRequest) -> JobRef: ...
    async def get_job_status(self, job_id: str) -> JobStatus: ...
    async def cancel_job(self, job_id: str) -> CancelResult: ...
    async def stream_job_events(self, job_id: str) -> AsyncIterator[JobEvent]: ...
```

### 4.2 `bridle.domain`

职责：

- 定义 Pydantic v2 领域模型；
- 作为 UI、Provider、Workflow、Godot 管线之间的稳定契约。

关键模型：

- `ProjectRef`
- `ProjectSummary`
- `ProviderId`
- `ProviderCapability`
- `ProviderHealth`
- `WorkflowRequest`
- `JobRef`
- `JobStatus`
- `JobEvent`
- `AssetGenerationRequest`
- `AssetJob`
- `GeneratedAsset`
- `ImportResult`
- `BridleError`

### 4.3 `bridle.harness.task_orchestrator`

职责：

- 管理后台 job 生命周期；
- 控制并发；
- 执行取消、重试、超时；
- 把阶段状态写入 SQLite；
- 把事件推送给 event bus。

MVP 实现：

- `asyncio.Queue(maxsize=N)`；
- 固定 worker pool；
- 每个 job 包含 workflow name、payload、project、stage、attempt；
- I/O 任务用 async；
- 阻塞任务用 `asyncio.to_thread()`；
- Godot CLI 用 async subprocess。

核心接口草案：

```python
class TaskOrchestrator:
    async def submit(self, job: JobSpec) -> JobRef: ...
    async def status(self, job_id: str) -> JobStatus: ...
    async def cancel(self, job_id: str) -> CancelResult: ...
    async def events(self, job_id: str) -> AsyncIterator[JobEvent]: ...
```

### 4.4 `bridle.harness.workflow`

职责：

- 把模板定义转换为可执行阶段；
- 每个阶段可重试、可取消、可记录；
- 工作流只依赖 capability，不依赖供应商类。

MVP 角色生成工作流阶段：

1. `validate_project`
2. `resolve_providers`
3. `submit_text_to_3d_preview`
4. `poll_preview`
5. `submit_refine`
6. `poll_refine`
7. `download_assets`
8. `inspect_glb`
9. `prepare_godot_files`
10. `run_godot_import_check`
11. `generate_sample_scene_or_script`
12. `finalize_asset_record`

### 4.5 `bridle.harness.event_bus`

职责：

- 为桌面 UI、CLI、日志和测试提供统一事件流；
- 保证长任务进度可见；
- 允许失败时定位阶段。

事件最小字段：

```python
class JobEvent(BaseModel):
    id: str
    job_id: str
    type: str
    stage: str | None
    message: str
    progress: float | None
    payload: dict[str, Any] = {}
    created_at: datetime
```

### 4.6 `bridle.harness.job_store`

职责：

- SQLite 持久化 job；
- 支持应用重启后查看历史；
- 为未来恢复任务保留阶段边界。

MVP 表：

- `projects`
- `provider_configs`
- `jobs`
- `job_events`
- `generated_assets`
- `benchmark_samples`

### 4.7 `bridle.providers.llm_litellm`

职责：

- 包装 LiteLLM SDK；
- 默认接入 DeepSeek；
- 转换 LiteLLM streaming chunk 为 Bridle `JobEvent` 或 `LLMEvent`；
- 保留 DeepSeek reasoner metadata；
- 映射错误类型。

约束：

- 业务层不直接 import LiteLLM；
- 所有 Key 从 `KeyResolver` 获取；
- 支持外部 Gateway URL 预留。

### 4.8 `bridle.providers.asset_meshy`

职责：

- 实现 Meshy Text-to-3D preview/refine；
- 轮询任务状态；
- 下载 GLB/纹理；
- 将 Meshy 原始响应转换为 `GeneratedAsset`。

约束：

- 不直接写 Godot 项目结构；
- 不阻塞调用方；
- 只通过 worker/orchestrator 执行；
- 所有 API 调用有 timeout/retry/cancellation check。

### 4.9 `bridle.godot`

职责：

- 识别 Godot 项目；
- 采集项目元数据；
- 管理生成资产输出目录；
- 检测 GLB；
- 生成 Godot 资源文件或示例脚本；
- 调用 Godot CLI 做导入校验。

MVP 目录约定：

```text
res://bridle/generated/<asset_id>/
  source/
    model.glb
    textures/
  godot/
    materials/
    preview_scene.tscn
    use_asset.gd
  bridle_asset.json
```

---

## 5. 异步 job 生命周期

```mermaid
stateDiagram-v2
    [*] --> created
    created --> queued
    queued --> running
    running --> waiting_provider
    waiting_provider --> running
    running --> downloading
    downloading --> importing
    importing --> succeeded
    running --> retrying
    retrying --> queued
    running --> failed
    waiting_provider --> failed
    downloading --> failed
    importing --> failed
    running --> cancel_requested
    waiting_provider --> cancel_requested
    downloading --> cancel_requested
    cancel_requested --> cancelled
    succeeded --> [*]
    failed --> [*]
    cancelled --> [*]
```

阶段规则：

- `created`：job 已创建但尚未入队；
- `queued`：等待 worker；
- `running`：本地步骤执行中；
- `waiting_provider`：外部 Provider 异步任务轮询中；
- `downloading`：下载资产；
- `importing`：GLB 检测或 Godot CLI 导入；
- `retrying`：可恢复错误等待重试；
- `failed`：不可恢复错误；
- `cancel_requested`：等待阶段边界取消；
- `cancelled`：已取消并落库。

---

## 6. 角色生成时序

```mermaid
sequenceDiagram
    participant UI as Tauri UI
    participant App as AppService
    participant Orchestrator as TaskOrchestrator
    participant Meshy as MeshyProvider
    participant Godot as GodotImportPipeline
    participant Store as JobStore/EventBus

    UI->>App: submit_workflow(prompt, project)
    App->>Orchestrator: submit(JobSpec)
    Orchestrator->>Store: job.created/job.queued
    App-->>UI: JobRef(job_id)

    UI->>App: stream_job_events(job_id)
    App-->>UI: JobEvent stream

    Orchestrator->>Meshy: create preview task
    Meshy-->>Orchestrator: provider_task_id
    Orchestrator->>Store: provider.polling
    loop until preview done
        Orchestrator->>Meshy: get task status
        Meshy-->>Orchestrator: status/progress
        Orchestrator->>Store: job.progress
    end

    Orchestrator->>Meshy: create refine task
    loop until refine done
        Orchestrator->>Meshy: get task status
        Meshy-->>Orchestrator: status/progress
        Orchestrator->>Store: job.progress
    end

    Orchestrator->>Meshy: download generated files
    Orchestrator->>Store: download.progress
    Orchestrator->>Godot: inspect + prepare files
    Orchestrator->>Godot: run Godot CLI import check
    Godot-->>Orchestrator: ImportResult
    Orchestrator->>Store: job.succeeded
    UI-->>App: get_job_status(job_id)
```

---

## 7. 错误模型

统一错误类型：

- `ConfigError`
- `AuthError`
- `ProviderCapabilityError`
- `ProviderRateLimitError`
- `ProviderTaskFailedError`
- `NetworkError`
- `DownloadError`
- `AssetValidationError`
- `GodotProjectError`
- `GodotCliError`
- `CancelledError`
- `InternalError`

错误必须包含：

- `code`
- `message`
- `stage`
- `provider_id`
- `retryable`
- `safe_details`

严禁包含：

- 完整 API Key；
- Authorization header；
- 带签名 URL；
- 用户本地敏感路径的非必要片段。

---

## 8. BYOK 设计

### 8.1 MVP 配置来源

优先级：

1. 运行时显式传入配置；
2. 项目级 `bridle.toml`；
3. 用户级配置；
4. 环境变量；
5. Provider 默认值。

MVP 可以先只实现环境变量 + TOML 元数据，但接口按优先级设计。

### 8.2 配置示例

```toml
[providers.llm.deepseek]
type = "llm"
backend = "litellm"
model = "deepseek/deepseek-chat"
api_key_env = "DEEPSEEK_API_KEY"
default_for = ["code", "context"]

[providers.asset.meshy]
type = "asset"
capabilities = ["model3d.text_to_3d", "texture.retexture", "rigging.auto_rig"]
api_key_env = "MESHY_API_KEY"
default_for = ["model3d"]

[godot]
executable = "godot"
generated_assets_dir = "res://bridle/generated"
```

### 8.3 连接测试

每个 Provider 必须实现或声明连接测试策略：

- LLM：轻量 model list 或最小 chat request；
- Meshy：账户/API endpoint ping 或最小权限检查；
- Godot CLI：`godot --version`；
- 项目：检测 `project.godot`。

---

## 9. Provider 能力模型

能力声明示例：

```python
class ProviderCapability(str, Enum):
    LLM_CHAT = "llm.chat"
    LLM_STREAM = "llm.stream"
    LLM_STRUCTURED_OUTPUT = "llm.structured_output"
    MODEL3D_TEXT_TO_3D = "model3d.text_to_3d"
    MODEL3D_IMAGE_TO_3D = "model3d.image_to_3d"
    TEXTURE_RETEXTURE = "texture.retexture"
    TEXTURE_PBR_GENERATE = "texture.pbr_generate"
    RIGGING_AUTO_RIG = "rigging.auto_rig"
    ANIMATION_VIDEO_TO_MOTION = "animation.video_to_motion"
```

工作流请求只声明需要能力：

```python
required_capabilities = [
    ProviderCapability.MODEL3D_TEXT_TO_3D,
]
```

Provider resolver 负责选择默认 Provider 或用户指定 Provider。

---

## 10. 桌面 UI MVP

MVP 最小页面：

1. **Project**
   - 选择 Godot 项目；
   - 显示 Godot 版本、插件、目录摘要；
   - 显示生成资产目录。

2. **Providers**
   - DeepSeek Key 状态；
   - Meshy Key 状态；
   - 连接测试；
   - 脱敏显示。

3. **Generate**
   - 角色描述输入；
   - 模型风格/low-poly 选项；
   - 目标目录；
   - 启动任务。

4. **Jobs**
   - 当前 job 进度；
   - 阶段日志；
   - 取消按钮；
   - 成功后的资产路径和打开提示。

约束：

- UI 不直接调用 Provider；
- UI 不直接执行 Godot CLI；
- UI 不等待长任务；
- UI 所有长任务状态来自 `JobEvent`。

---

## 11. 测试设计

### 11.1 单元测试

- Pydantic domain model 校验；
- capability resolver；
- KeyResolver 脱敏；
- error mapping；
- job state transition；
- output path normalization。

### 11.2 集成测试

- LiteLLM DeepSeek mock/录制；
- Meshy mock/录制；
- Godot 项目 fixture；
- Godot CLI 可选测试；
- GLB fixture 检测。

### 11.3 桌面响应性测试

- 提交模拟 60 秒 job；
- UI 必须可继续响应；
- 进度事件持续刷新；
- 取消能进入 `cancel_requested` / `cancelled`；
- Tauri command 不超过短时阈值。

### 11.4 性能基线

- LLM 首 token；
- Provider 轮询间隔；
- 下载吞吐；
- GLB 检测耗时；
- Godot CLI 导入耗时；
- job event 延迟。

---

## 12. MVP 交付切片

建议按以下纵向切片实现：

### Slice 1：桌面壳 + Python sidecar ping

- Tauri 主窗口；
- Python sidecar 启动；
- `get_version()` / `health()`；
- 事件通道打通。

### Slice 2：项目选择 + 元数据

- 选择 Godot 项目；
- 检测 `project.godot`；
- 显示项目摘要；
- 保存最近项目。

### Slice 3：BYOK + DeepSeek 连接测试

- 环境变量读取；
- Key 脱敏；
- LiteLLM facade；
- DeepSeek 连接测试。

### Slice 4：异步 job 引擎

- `submit_job`；
- `stream_job_events`；
- `cancel_job`；
- SQLite job store；
- 模拟长任务验证 UI 不冻结。

### Slice 5：Meshy Provider

- Text-to-3D preview；
- refine；
- 轮询；
- 下载；
- 事件进度。

### Slice 6：Godot 导入管线

- 输出目录；
- GLB 检测；
- 贴图整理；
- Godot CLI import check；
- 示例脚本/场景。

### Slice 7：角色生成闭环

- 模板参数；
- Provider resolution；
- 完整 job；
- 结果面板；
- 错误和取消路径。

---

## 13. 待设计细化

下一阶段需要进入详细设计：

1. `JobEvent` / `JobStatus` / `JobSpec` Pydantic schema；
2. SQLite schema；
3. Tauri ↔ Python sidecar 通信方式；
4. Meshy API adapter 详细状态映射；
5. Godot 生成目录和 `.tscn/.tres` 写入规范；
6. 桌面 UI 信息架构和页面原型；
7. Provider 插件加载机制。

