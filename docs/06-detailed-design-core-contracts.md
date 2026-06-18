# godot-bridle 核心契约详细设计

> **文档版本**：v0.1
> **创建日期**：2026-06-18
> **阶段**：详细设计
> **依赖文档**：
> - [04-architecture-decisions.md](04-architecture-decisions.md) v0.1
> - [05-system-design.md](05-system-design.md) v0.2
> **状态**：待评审

---

## 1. 范围

本文固定 MVP 实现前的核心契约：

- Pydantic domain schema；
- SQLite schema；
- stdio JSON-RPC 消息协议；
- Async Task Orchestrator 接口；
- Meshy Provider 状态映射；
- Godot 生成目录与资产清单；
- 错误、日志、脱敏基础规则。

---

## 2. 命名与 ID 规则

| 对象 | 格式 | 示例 |
|---|---|---|
| `job_id` | `job_` + ULID/UUIDv7 | `job_01J...` |
| `event_id` | `evt_` + ULID/UUIDv7 | `evt_01J...` |
| `asset_id` | `asset_` + slug + short hash | `asset_low_poly_knight_a13f9c` |
| `provider_id` | lowercase dotted/string id | `deepseek`, `meshy` |
| `workflow_id` | lowercase snake/dotted id | `character_gen` |
| `stage` | lowercase snake_case | `download_assets` |

路径规则：

- 所有用户可见生成物必须位于 Godot 项目根目录内；
- MVP 默认输出目录为 `res://bridle/generated/<asset_id>/`；
- 文件系统内部使用绝对路径，展示给用户时优先显示 Godot `res://` 路径；
- 任何来自 Provider 的文件名都必须 sanitize，不直接作为落盘路径。

---

## 3. Pydantic Schema

### 3.1 基础类型

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

NonEmptyStr = Annotated[str, Field(min_length=1)]
Progress = Annotated[float, Field(ge=0.0, le=1.0)]
```

### 3.2 Capability

`ProviderCapability` 的 canonical source 是 ADR-005。下面的代码是实现镜像，用于固定 MVP schema 形态；后续新增或改名能力时必须先更新 ADR-005，再同步到 `bridle/domain/capabilities.py` 和相关测试。

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
    ANIMATION_TEXT_TO_MOTION = "animation.text_to_motion"
```

### 3.3 Project

```python
class ProjectRef(BaseModel):
    root_path: Path
    godot_project_file: Path


class ProjectSummary(BaseModel):
    root_path: Path
    godot_version: str | None = None
    project_name: str | None = None
    enabled_plugins: list[str] = []
    addons: list[str] = []
    gdscript_files_count: int = 0
    scene_files_count: int = 0
    resource_files_count: int = 0
    generated_assets_dir: str = "res://bridle/generated"
    warnings: list[str] = []
```

### 3.4 Provider

```python
class ProviderKind(str, Enum):
    LLM = "llm"
    ASSET = "asset"
    GATEWAY = "gateway"


class ProviderConfig(BaseModel):
    provider_id: NonEmptyStr
    kind: ProviderKind
    backend: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    capabilities: list[ProviderCapability] = []
    default_for: list[ProviderCapability] = []
    timeout_seconds: float = 60.0
    max_retries: int = 2


class ProviderSummary(BaseModel):
    provider_id: str
    kind: ProviderKind
    configured: bool
    key_source: Literal["env", "keyring", "none", "unknown"] = "unknown"
    key_preview: str | None = None
    capabilities: list[ProviderCapability]
    default_for: list[ProviderCapability] = []


class ProviderHealthStatus(str, Enum):
    OK = "ok"
    MISSING_KEY = "missing_key"
    AUTH_FAILED = "auth_failed"
    NETWORK_FAILED = "network_failed"
    UNSUPPORTED = "unsupported"
    UNKNOWN_FAILED = "unknown_failed"


class ProviderHealth(BaseModel):
    provider_id: str
    status: ProviderHealthStatus
    latency_ms: int | None = None
    message: str
    safe_details: str | None = None
```

### 3.5 Workflow

```python
class WorkflowRequest(BaseModel):
    workflow_id: str
    project_root: Path
    prompt: str
    requested_capabilities: list[ProviderCapability]
    explicit_providers: dict[str, str] = {}
    params: dict[str, JsonValue] = {}


class ProviderPlan(BaseModel):
    llm_provider_id: str | None = None
    model3d_provider_id: str | None = None
    texture_provider_id: str | None = None
    rigging_provider_id: str | None = None
    animation_provider_id: str | None = None
```

### 3.6 Job

```python
class JobState(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_PROVIDER = "waiting_provider"
    DOWNLOADING = "downloading"
    IMPORTING = "importing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class JobSpec(BaseModel):
    workflow_id: str
    project_root: Path
    request: WorkflowRequest
    provider_plan: ProviderPlan | None = None
    idempotency_key: str | None = None


class JobRef(BaseModel):
    job_id: str
    state: JobState
    created_at: datetime


class JobStatus(BaseModel):
    job_id: str
    workflow_id: str
    state: JobState
    stage: str | None = None
    progress: Progress | None = None
    message: str | None = None
    error: "BridleError" | None = None
    asset_id: str | None = None
    created_at: datetime
    updated_at: datetime
```

### 3.7 Event

```python
class JobEventType(str, Enum):
    JOB_CREATED = "job.created"
    JOB_STARTED = "job.started"
    JOB_PROGRESS = "job.progress"
    PROVIDER_REQUESTED = "provider.requested"
    PROVIDER_POLLING = "provider.polling"
    PROVIDER_COMPLETED = "provider.completed"
    DOWNLOAD_STARTED = "download.started"
    DOWNLOAD_PROGRESS = "download.progress"
    GODOT_CLI_STARTED = "godot_cli.started"
    GODOT_CLI_COMPLETED = "godot_cli.completed"
    JOB_RETRYING = "job.retrying"
    JOB_FAILED = "job.failed"
    JOB_SUCCEEDED = "job.succeeded"
    JOB_CANCELLED = "job.cancelled"
    LOG = "log"


class JobEvent(BaseModel):
    id: str
    sequence: int
    job_id: str
    type: JobEventType
    stage: str | None = None
    message: str
    progress: Progress | None = None
    payload: dict[str, JsonValue] = {}
    created_at: datetime
```

### 3.8 Error

```python
class BridleErrorCode(str, Enum):
    CONFIG_ERROR = "config_error"
    AUTH_ERROR = "auth_error"
    PROVIDER_CAPABILITY_ERROR = "provider_capability_error"
    PROVIDER_RATE_LIMIT_ERROR = "provider_rate_limit_error"
    PROVIDER_TASK_FAILED_ERROR = "provider_task_failed_error"
    NETWORK_ERROR = "network_error"
    DOWNLOAD_ERROR = "download_error"
    ASSET_VALIDATION_ERROR = "asset_validation_error"
    GODOT_PROJECT_ERROR = "godot_project_error"
    GODOT_CLI_ERROR = "godot_cli_error"
    CANCELLED_ERROR = "cancelled_error"
    INTERNAL_ERROR = "internal_error"


class BridleError(BaseModel):
    code: BridleErrorCode
    message: str
    stage: str | None = None
    provider_id: str | None = None
    retryable: bool = False
    safe_details: str = ""
```

### 3.9 Asset

```python
class DownloadedAssetBundle(BaseModel):
    asset_id: str
    model_glb_path: Path
    texture_paths: list[Path] = []
    provider_id: str
    provider_task_id: str | None = None
    provider_metadata: dict[str, JsonValue] = {}


class GlbInspectionReport(BaseModel):
    asset_id: str
    parse_ok: bool
    vertex_count: int | None = None
    mesh_count: int | None = None
    material_count: int | None = None
    dimensions: tuple[float, float, float] | None = None
    texture_refs: list[str] = []
    warnings: list[str] = []


class ImportResult(BaseModel):
    asset_id: str
    ok: bool
    exit_code: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    warnings: list[str] = []


class GeneratedAssetRecord(BaseModel):
    asset_id: str
    project_root: Path
    res_path: str
    provider_id: str
    source_files: list[str]
    godot_files: list[str]
    status: Literal["ready", "partial", "failed"]
    created_at: datetime
```

---

## 4. SQLite Schema

MVP 可以先使用 `sqlite3` + migrations 目录。所有 JSON 字段存储为 TEXT，并由 Pydantic 负责序列化/反序列化。

### 4.1 `projects`

```sql
CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  root_path TEXT NOT NULL UNIQUE,
  project_name TEXT,
  godot_version TEXT,
  generated_assets_dir TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 4.2 `provider_configs`

```sql
CREATE TABLE provider_configs (
  provider_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  backend TEXT,
  model TEXT,
  base_url TEXT,
  api_key_env TEXT,
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  default_for_json TEXT NOT NULL DEFAULT '[]',
  key_source TEXT NOT NULL DEFAULT 'none',
  last_health_status TEXT,
  last_health_message TEXT,
  last_checked_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

禁止字段：

- `api_key`
- `secret`
- `token`
- `authorization`

### 4.3 `jobs`

```sql
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL,
  project_root TEXT NOT NULL,
  state TEXT NOT NULL,
  stage TEXT,
  progress REAL,
  message TEXT,
  request_json TEXT NOT NULL,
  provider_plan_json TEXT,
  asset_id TEXT,
  error_json TEXT,
  idempotency_key TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE INDEX idx_jobs_project_root ON jobs(project_root);
CREATE INDEX idx_jobs_state ON jobs(state);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
```

### 4.4 `job_events`

```sql
CREATE TABLE job_events (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  type TEXT NOT NULL,
  stage TEXT,
  message TEXT NOT NULL,
  progress REAL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  level TEXT NOT NULL DEFAULT 'info',
  created_at TEXT NOT NULL,
  FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);

CREATE UNIQUE INDEX idx_job_events_job_sequence ON job_events(job_id, sequence);
CREATE INDEX idx_job_events_job_created ON job_events(job_id, created_at);
```

事件顺序规则：

- `sequence` 在单个 job 内从 1 递增；
- event bus 推送前必须先落库；
- 订阅时用 `(job_id, sequence > after_sequence)` 重放。

### 4.5 `generated_assets`

```sql
CREATE TABLE generated_assets (
  asset_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  project_root TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  res_path TEXT NOT NULL,
  status TEXT NOT NULL,
  source_files_json TEXT NOT NULL DEFAULT '[]',
  godot_files_json TEXT NOT NULL DEFAULT '[]',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  sha256_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);

CREATE INDEX idx_generated_assets_project ON generated_assets(project_root);
```

### 4.6 `benchmark_samples`

```sql
CREATE TABLE benchmark_samples (
  id TEXT PRIMARY KEY,
  job_id TEXT,
  metric_name TEXT NOT NULL,
  stage TEXT,
  provider_id TEXT,
  duration_ms INTEGER,
  value REAL,
  unit TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX idx_benchmark_job ON benchmark_samples(job_id);
CREATE INDEX idx_benchmark_metric ON benchmark_samples(metric_name);
```

---

## 5. stdio JSON-RPC Protocol

### 5.1 Envelope

Request:

```json
{
  "jsonrpc": "2.0",
  "protocol_version": "2026-06-18",
  "id": "req_001",
  "method": "submit_workflow",
  "params": {}
}
```

Response:

```json
{
  "jsonrpc": "2.0",
  "protocol_version": "2026-06-18",
  "id": "req_001",
  "result": {}
}
```

Error response:

```json
{
  "jsonrpc": "2.0",
  "protocol_version": "2026-06-18",
  "id": "req_001",
  "error": {
    "code": "config_error",
    "message": "Provider is missing API key.",
    "safe_details": "Set DEEPSEEK_API_KEY and retry."
  }
}
```

Notification:

```json
{
  "jsonrpc": "2.0",
  "protocol_version": "2026-06-18",
  "method": "job.event",
  "params": {
    "job_id": "job_...",
    "event": {}
  }
}
```

### 5.2 Methods

| Method | Params | Result | Notes |
|---|---|---|---|
| `health` | `{}` | `{ "ok": true, "version": "..." }` | sidecar ping |
| `open_project` | `ProjectOpenParams` | `ProjectSummary` | short operation |
| `list_providers` | `{}` | `ProviderSummary[]` | no secrets |
| `test_provider` | `{ "provider_id": "deepseek" }` | `ProviderHealth` | may take seconds but should not be long-running |
| `submit_workflow` | `WorkflowRequest` | `JobRef` | long task submission only |
| `get_job_status` | `{ "job_id": "..." }` | `JobStatus` | short operation |
| `cancel_job` | `{ "job_id": "..." }` | `CancelResult` | transitions to cancel_requested |
| `stream_job_events` | `{ "job_id": "...", "after_sequence": 0 }` | `{ "subscribed": true }` | sidecar then sends `job.event` notifications |

### 5.3 Sidecar Startup

On ready:

```json
{
  "jsonrpc": "2.0",
  "protocol_version": "2026-06-18",
  "method": "sidecar.ready",
  "params": {
    "version": "0.1.0",
    "pid": 12345
  }
}
```

### 5.4 Event Replay

`stream_job_events` must:

1. read historical `job_events` from SQLite using `after_sequence`;
2. emit each historical event as `job.event`;
3. register the client for live events;
4. emit future events in sequence order.

The desktop must tolerate duplicate events by using `(job_id, sequence)` as the idempotency key.

---

## 6. Async Task Orchestrator

### 6.1 Responsibilities

- Validate job spec;
- assign job id;
- persist `created` and `queued`;
- enqueue job;
- run workflow stages in worker;
- persist every state transition;
- publish events after persistence;
- support cancellation at stage boundaries;
- map exceptions to `BridleError`.

### 6.2 Cancellation

Cancellation is cooperative:

- `cancel_job()` sets state to `cancel_requested`;
- Provider polling checks cancellation before each poll;
- downloads check cancellation between chunks;
- Godot CLI cancellation attempts subprocess terminate, then kill after timeout;
- blocking `to_thread()` work may only cancel after returning, so it must be kept bounded.

### 6.3 Retry

MVP retry policy:

| Error | Retry | Notes |
|---|---|---|
| Network timeout | yes | exponential backoff |
| 429/rate limit | yes | respect retry-after if present |
| Provider task failed | no by default | user can rerun job |
| Download interrupted | yes | if URL still valid |
| GLB parse failed | no | asset validation error |
| Godot CLI failed | no by default | preserve logs |

Backoff:

- base: 1s;
- multiplier: 2;
- max: 30s;
- jitter: yes;
- max attempts: provider config `max_retries`.

---

## 7. Meshy Adapter Mapping

### 7.1 MVP Operations

MVP supports:

- create Text-to-3D preview task;
- poll preview task;
- create refine task;
- poll refine task;
- download GLB and textures.

### 7.2 Internal Stage Mapping

| Bridle Stage | Meshy Operation | Bridle State |
|---|---|---|
| `submit_text_to_3d_preview` | POST preview task | `running` |
| `poll_preview` | GET task until complete | `waiting_provider` |
| `submit_refine` | POST refine task | `running` |
| `poll_refine` | GET task until complete | `waiting_provider` |
| `download_assets` | GET file URLs | `downloading` |

### 7.3 Provider Status Mapping

Exact Meshy statuses must be confirmed during implementation against current docs/API response, but adapter must normalize into:

| Provider status class | Bridle handling |
|---|---|
| queued/pending | `waiting_provider`, progress from provider if available |
| running/in_progress | `waiting_provider`, emit `provider.polling` |
| succeeded/completed | continue to next stage |
| failed/error | `ProviderTaskFailedError` |
| cancelled/expired | `ProviderTaskFailedError`, retryable false |
| unknown | `ProviderTaskFailedError`, safe_details includes sanitized raw status |

### 7.4 Polling Policy

- initial delay: 2s;
- interval: 5s;
- max interval: 15s;
- max task duration: configurable, default 10 minutes;
- every poll emits at most one `provider.polling` event unless progress changed;
- cancellation checked before each poll.

### 7.5 Download Rules

- download via `httpx.AsyncClient.stream`;
- write to temp file first: `<name>.part`;
- compute sha256 while streaming;
- atomically rename after success;
- emit `download.progress` when bytes read changes by at least 1 MB or 500 ms;
- enforce max file size from config.

---

## 8. Godot Output Contract

### 8.1 Directory Layout

```text
res://bridle/generated/<asset_id>/
  source/
    model.glb
    textures/
  godot/
    materials/
    preview_scene.tscn
    use_asset.gd
  logs/
    godot_import_stdout.txt
    godot_import_stderr.txt
  bridle_asset.json
```

### 8.2 `bridle_asset.json`

```json
{
  "asset_id": "asset_low_poly_knight_a13f9c",
  "job_id": "job_...",
  "provider_id": "meshy",
  "status": "ready",
  "source": {
    "model": "res://bridle/generated/.../source/model.glb",
    "textures": []
  },
  "godot": {
    "preview_scene": "res://bridle/generated/.../godot/preview_scene.tscn",
    "script": "res://bridle/generated/.../godot/use_asset.gd"
  },
  "inspection": {
    "parse_ok": true,
    "warnings": []
  },
  "sha256": {
    "model.glb": "..."
  },
  "created_at": "2026-06-18T00:00:00Z"
}
```

### 8.3 Write Safety

- create output dir only under `res://bridle/generated`;
- if target `asset_id` exists, use resume mode only when job id matches or user confirms overwrite;
- write generated files to temp names first;
- final manifest write is last;
- incomplete jobs leave `status = "partial"` or no manifest.

---

## 9. Open Questions For Implementation

1. Tauri sidecar packaging details for Python on Windows/macOS/Linux;
2. exact Meshy response fields and status values;
3. Godot CLI import command shape for target Godot 4.6+;
4. whether to use SQLModel/SQLAlchemy or handwritten SQL migrations;
5. first UI component library for Tauri frontend.
