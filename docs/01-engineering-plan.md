# godot-bridle 软件工程实施计划

> **文档版本**：v0.2
> **创建日期**：2026-06-18
> **依赖文档**：[00-initial-need-and-situation.md](00-initial-need-and-situation.md) v0.2
> **架构决策**：[04-architecture-decisions.md](04-architecture-decisions.md) v0.1
> **状态**：待执行

---

## 一、项目初始化（本周）

### 1.1 仓库与工具链

- [ ] 创建 GitHub 仓库 `godot-bridle`，MIT 协议
- [ ] 配置 `.gitignore`（Python + Node + Godot 项目残留）
- [ ] 初始化 Python 项目：uv 优先（Poetry 备选），Python 3.11+
- [ ] 初始化桌面应用：Tauri v2 + TypeScript（PySide6 作为备选方案，不走 WebUI 主路线）
- [ ] 配置 ruff（Python lint）+ prettier（前端格式化）
- [ ] 配置 pre-commit hooks
- [ ] 创建 Discord 服务器

### 1.2 目录结构（初步）

```
godot-bridle/
├── bridle/                    # Python 核心包
│   ├── __init__.py
│   ├── app/                   # 桌面应用调用的 application service 层
│   │   ├── __init__.py
│   │   ├── services.py
│   │   ├── desktop_api.py
│   │   └── cli.py             # 薄 CLI 接口，测试/调试/自动化用
│   ├── domain/                # 领域模型：Pydantic v2
│   │   ├── __init__.py
│   │   ├── assets.py
│   │   ├── capabilities.py
│   │   ├── config.py
│   │   ├── events.py
│   │   ├── jobs.py
│   │   └── llm.py
│   ├── harness/               # Harness 基础设施层 (5.4)
│   │   ├── __init__.py
│   │   ├── benchmark.py       # Harness 性能基线
│   │   ├── cache.py           # 精确缓存 + 内容哈希缓存
│   │   ├── errors.py          # 统一错误分类
│   │   ├── event_bus.py       # 进度/日志/桌面事件流
│   │   ├── job_store.py       # SQLite job 状态
│   │   ├── task_orchestrator.py # 异步任务编排引擎
│   │   ├── workers.py         # Provider/下载/Godot CLI worker
│   │   └── workflow.py        # 轻量工作流状态机
│   ├── providers/             # Provider 适配层
│   │   ├── __init__.py
│   │   ├── base.py            # Asset Provider 抽象 + facade 协议
│   │   ├── llm_litellm.py     # LiteLLM SDK facade，DeepSeek 默认
│   │   └── asset_meshy.py     # Meshy MVP Provider
│   ├── godot/                 # Godot 通信层
│   │   ├── __init__.py
│   │   ├── project.py         # 项目识别和元数据采集
│   │   ├── import_pipeline.py # GLB 检测/导入/材质处理
│   │   └── cli.py             # Godot --script / --headless 调用
│   └── config/                # 配置管理
│       ├── __init__.py
│       ├── settings.py        # TOML + Pydantic Settings
│       └── key_resolver.py    # BYOK：环境变量、脱敏、P1 keyring
├── desktop/                   # Tauri v2 桌面应用
├── tests/                     # 测试
│   ├── unit/
│   ├── integration/
│   └── fixtures/              # 测试用 Godot 项目
├── templates/                 # 工作流模板
│   └── character_gen/         # "角色生成"模板 (FR21)
├── docs/                      # 文档
├── pyproject.toml             # Python 项目配置
├── README.md
└── LICENSE
```

---

## 二、MVP 开发计划（Phase 1：2026 年 7 月 - 10 月）

### 迭代 1：桌面优先骨架 + Harness 领域内核（第 1-2 周）

| 任务 | 关联 FR | 产出 |
|---|---|---|
| 搭建 Tauri v2 桌面应用骨架 | FR1 | `desktop/` |
| 搭建 Python application service | FR1 | `bridle/app/services.py` |
| 定义 Pydantic 领域模型 | FR27-FR28 | `bridle/domain/` |
| 定义 Asset Provider 抽象和 capability 模型 | FR28 | `bridle/providers/base.py` |
| 实现 TOML 配置管理 | FR15 | `bridle/config/settings.py` |
| 实现 BYOK Key Resolver（环境变量 + 脱敏） | FR15 | `bridle/config/key_resolver.py` |
| 建立 SQLite job store | FR23 | `bridle/harness/job_store.py` |
| 实现异步任务编排引擎骨架 | RA-P0-15 | `bridle/harness/task_orchestrator.py` |
| 实现桌面 job 提交/查询/取消 API | RA-P0-15 | `bridle/app/services.py` |
| 编写领域模型和配置测试 | FR27-FR28 | `tests/unit/` |

### 迭代 2：LiteLLM + DeepSeek + 桌面 BYOK（第 3-4 周）

| 任务 | 关联 FR | 产出 |
|---|---|---|
| 实现 LiteLLM facade | FR27, FR29 | `bridle/providers/llm_litellm.py` |
| 接入 DeepSeek 默认配置 | FR5, FR29 | `deepseek/deepseek-chat` |
| 实现 LLM stream 到 Bridle event 的转换 | FR29 | `bridle/domain/events.py` |
| 实现 Provider 连接测试 | FR15, FR23 | `bridle/app/services.py` |
| 实现桌面设置页最小 BYOK 流程 | FR1, FR15 | `desktop/` |
| 实现精确缓存和内容哈希缓存 | FR30 | `bridle/harness/cache.py` |
| 验证长任务不阻塞 Tauri UI | RA-P0-15 | 后台 job + 事件流测试 |
| 编写 LiteLLM/DeepSeek 集成测试 | FR5-FR6 | `tests/integration/test_llm_litellm.py` |

### 迭代 3：Asset Provider + GLB 导入引擎（第 5-8 周）

| 任务 | 关联 FR | 产出 |
|---|---|---|
| 实现 Meshy 适配器（3D + 纹理 + 绑定） | FR7-FR8, FR31-FR32 | `bridle/providers/asset/meshy.py` |
| 将 Meshy preview/refine/轮询封装为后台 job | RA-P0-15 | `bridle/harness/workflow.py` |
| 实现元数据采集器（Godot 版本/插件/文件结构） | FR2-FR4 | `bridle/godot/project.py` |
| 实现 LLM 上下文桥 | — | `bridle/app/services.py` |
| 实现文件系统桥接（读写 .tscn/.tres/.gd） | — | `bridle/godot/project.py` |
| 实现 GLB 导入检测引擎（解析/缩放/材质/路径） | FR9-FR14 | `bridle/godot/import_pipeline.py` |
| 将下载、GLB 检测、Godot CLI 导入封装为 worker 任务 | RA-P0-15 | `bridle/harness/workers.py` |
| 编写 Asset Provider 集成测试 | FR7-FR14 | `tests/integration/test_asset_providers.py` |

### 迭代 4：桌面体验 + 模板 + 发布（第 9-12 周）

| 任务 | 关联 FR | 产出 |
|---|---|---|
| 完善桌面主窗口（项目管理 + 工作流入口） | FR1 | `desktop/` |
| 实现桌面进度/日志/资产结果面板 | — | `desktop/` |
| 实现设置面板（Provider 配置 + Key 管理） | FR15 | `desktop/` |
| 实现"角色生成"工作流模板 | FR21 | `templates/character_gen/` |
| 实现错误处理框架 | FR23 | 全局错误处理 |
| 实现结构化日志 | FR24 | structlog 集成 |
| 内部测试 + Bug 修复 | — | — |
| 发布 v0.1-alpha 到 GitHub + Godot Asset Store | FR25 | Release |

---

## 三、Phase 2 预规划（2027 Q1）

| 迭代 | 内容 |
|---|---|
| 迭代 5 | Tripo Provider；Meshy Retexture/Auto-Rigging；纹理/动画 Provider 扩展 |
| 迭代 6 | LiteLLM Proxy/Bifrost 可选后端；Provider 容灾回退链；OpenTelemetry 集成 |
| 迭代 7 | 场景搭建模板 + 中文 UI；内部测试 |
| 迭代 8 | Godot Asset Store 付费模板准备 |

---

## 四、测试策略

| 层级 | 范围 | 工具 |
|---|---|---|
| **单元测试** | Provider 接口、缓存逻辑、GLB 修复算法 | pytest |
| **集成测试** | LLM/Asset API 真实调用（需 API Key） | pytest + vcr.py（录制回放） |
| **端到端测试** | 完整工作流：输入 prompt → 生成 → 导入 Godot 项目 | 手动 + 未来自动化 |
| **性能测试** | 缓存命中率、流式响应延迟、GLB 处理吞吐 | pytest-benchmark |

---

## 五、CI/CD

- GitHub Actions：lint（ruff）+ 单元测试 + 集成测试（API Key 通过 Secrets）
- release-it：版本发布 + Changelog 自动生成
- PyPI 发布（Phase 2）

---

## 六、开发规范

- **代码风格**：ruff（Python）、遵循 Google Python Style Guide
- **类型标注**：所有公共 API 必须完整类型标注（mypy strict）
- **文档**：docstring（Google style）+ README 快速入门
- **Git 提交**：Conventional Commits（`feat:`, `fix:`, `docs:`, `refactor:`）
- **分支策略**：`main`（稳定） + `develop`（开发） + `feat/*`（功能分支）
- **PR 审查**：至少 1 人审查，CI 全绿方可合并
