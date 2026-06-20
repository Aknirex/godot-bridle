# godot-bridle 开发进度评估与下一步计划

## 当前状态：v0.1.0a0（预发布 Alpha）

### 代码实现完成度

| 工作包 | 状态 | 说明 |
|--------|------|------|
| **WP0** 工具链 | ✅ 完成 | pyproject.toml, hatchling, uv, ruff, pytest |
| **WP1** 核心契约与配置 | ✅ 完成 | 8 个领域模型, 10 个能力枚举, 密钥掩码, TOML 配置解析 |
| **WP2** 任务存储/事件/编排器 | ✅ 完成 | SQLite 4 次迁移, WAL 模式, 任务恢复, 双写事件总线, 异步任务队列 |
| **WP3** stdio JSON-RPC Sidecar | ✅ 完成 | 10 个 RPC 方法, job.event 流式推送, 事件回放, 错误码映射 |
| **WP4** Provider 门面 | ✅ 完成 | LiteLLM (DeepSeek), Meshy (真实 + Mock), 能力匹配解析器 |
| **WP5** Godot 集成 | ✅ 完成 | 项目检测, 资源下载器, GLB 检测, 导入管线, Godot CLI 桥接 |
| **WP6** 角色生成工作流 | ✅ 完成 | 12 阶段管线, Prompt 增强, 重试/轮询/取消, Mock 全程 |
| **WP7** Tauri 桌面 MVP | ✅ 完成 | 4 页单窗口, Sidecar 管理 (Rust), 事件流送前端 |
| **WP8** 测试/基准/发布准备 | ✅ 完成 | 26 测试文件 / 78 条通过, benchmarking, 打包脚本 |

| 增强项 | 状态 | 说明 |
|--------|------|------|
| **P1 RAG 知识库 (K1-K4)** | ✅ 完成 | Chroma 持久化, 项目扫描, GDScript/MD/TSCN 分块, 查询服务, Sidecar 集成 |

---

## Alpha 退出标准对照

| 标准 | 状态 |
|------|------|
| 桌面应用可打开真实 Godot 项目 | ✅ |
| 用户可配置 DeepSeek/Meshy key，连接测试通过 | ✅ |
| 任务提交即返回 job_id，UI 非阻塞 | ✅ |
| 完整管线（生成→导入）在后台 job 执行 | ✅ |
| 事件可回放完整历史 | ✅ |
| `bridle_asset.json` 生成在真实项目中 | ✅ |
| 失败展示统一错误码 + 脱敏 safe_details | ✅ |
| 默认测试全部通过 | ✅ (78 pass) |
| 日志中无明文 API key | ✅ |

---

## 仍待完成

### 一、生产就绪（优先级 P0——发版阻塞）

| 项目 | 当前 | 目标 |
|------|------|------|
| **CI/CD 管线** | 无 | GitHub Actions: ruff → pytest → cargo check → build |
| **纯净环境实机测试** | 仅开发机 | 洁净 Linux VM 上完整走通 mock 路径 |
| **生产级 Embedding Provider** | `DeterministicEmbeddingProvider`（hash 模拟） | 接入真实 embedding 模型（如 DeepSeek embedding 或 litellm embedding） |
| **Windows 打包** | 无 | Tauri + PyInstaller 交叉构建，MSI 安装器 |
| **文档补全** | 核心设计文档齐全 | 用户文档（快速入门、配置指南）、API 参考自动生成 |

### 二、MVP 增强（优先级 P1——v0.1 目标）

| 项目 | 说明 |
|------|------|
| **RAG 诊断集成 (K5)** | Godot 导入失败时检索相似错误和规则，生成诊断事件 |
| **RAG 桌面可视化 (K6)** | Knowledge/Assistant 页面展示索引状态、引用片段、相似度 |
| **反压与限流** | Sidecar 层增加 job 队列上限和 provider 并发控制 |
| **错误恢复粒度** | 区分可重试错误与不可重试错误，支持断点续传 |
| **更多 Provider** | Claude、GPT（通过 LiteLLM 覆盖），Tripo（v0.2 预研） |

### 三、Godot 编辑器集成（优先级 P1）

| 项目 | 说明 |
|------|------|
| **Godot 插件骨架** | `addons/bridle/plugin.cfg` + `bridle_editor.gd`，在 Godot 编辑器内启动/管理 sidecar |
| **编辑器面板** | 项目设置面板、生成面板、进度面板，复用桌面端协议 |
| **自动导入流程** | 资产生成完成后触发 Godot `EditorFileSystem.scan()` |

### 四、架构增强（优先级 P2——v0.2 预备）

| 项目 | 说明 |
|------|------|
| **Provider 容灾回退** | 主 provider 不可用时自动切换备用 provider |
| **OpenTelemetry 集成** | 分布式追踪覆盖完整 job 管线 |
| **加密密钥存储** | `api_key_env` 之外支持 keyring/加密存储 |
| **中文 UI** | 多语言框架 + 中文翻译 |

---

## 建议实施顺序

```
当前 ──────────────────────────────────────────► v0.1-alpha 发布 ────────► v0.1 MVP (10月)
       ↑                                                    ↑
       周 1-2                                                周 3-6
```

### 阶段 A：Alpha 收口（1-2 周）

1. **搭建 GitHub Actions CI**：lint → test → cargo check 流水线
2. **洁净 Linux 环境验证**：Docker/VM 上从零构建，走通 mock 验收路径
3. **真实 embedding provider 接入**：替换 `DeterministicEmbeddingProvider` 为 litellm embedding
4. **RAG 桌面可视化 (K6)**：Knowledge 页面骨架 + 索引状态展示
5. **打 tag 发布 v0.1.0a1**，输出 Linux AppImage

### 阶段 B：MVP 补全（3-4 周）

1. **Windows 打包支持**：Tauri MSI + PyInstaller Windows 构建
2. **Godot 编辑器插件**：项目内 `addons/bridle/` 启动 sidecar
3. **RAG 诊断集成 (K5)**：导入失败关联知识库
4. **用户文档上线**：README 更新、配置指南、API 文档
5. **Provider 扩展**：Claude、GPT 可用性验证
6. **v0.1.0 发布**：首个正式 MVP 版本

---

## 风险提示

| 风险 | 等级 | 缓解 |
|------|------|------|
| ChromaDB 嵌入依赖体积大（~800MB onnxruntime） | 中 | 保持 `knowledge` 为可选依赖组，默认不安装 |
| Windows 跨平台打包复杂度 | 中 | Rust 交叉编译 + PyInstaller wine 方案；可推迟到 v0.2 |
| 真实 embedding provider 延迟 & 成本 | 低 | 复用 BYOK 架构，默认用 DeepSeek cheap embedding |
| Godot 插件需 GDScript 开发能力 | 低 | 插件仅负责启动 sidecar + 文件刷新，逻辑在 Python |
