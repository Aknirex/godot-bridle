# 验证债务与后续开发计划

> **最后更新**：2026-06-21
> **当前阶段**：D5（Alpha 验证债务清零）— D1-D4 代码实现完成

## 1. 目的

当前代码已覆盖 v0.1-alpha 的全部功能闭环（WP0-WP8）及 P1 RAG 增强（K1-K6）。为了保持开发节奏，本文将暂时不执行的发布验证显式登记为**验证债务**，同时固定下一阶段的开发顺序。

暂缓验证不代表验收通过。以下验证债务必须在创建 `v0.1-alpha` release、上传安装包或宣称平台支持前清零。

### 1.1 最新代码健康检查（2026-06-21）

| 检查项 | 结果 |
|--------|------|
| Python 测试 | ✅ 100 passed, 1 skipped, 3 deselected |
| Ruff lint | ✅ All checks passed |
| CLI health | ✅ `{"status":"ok"}` |
| TypeScript 测试 (Vitest) | ✅ 7 passed (3 files) |
| TypeScript 编译 | ✅ 零错误 |
| Vite 生产构建 | ✅ 193ms |
| Rust check | ⏳ 未在 Windows 本地执行（CI ubuntu-latest 覆盖） |

自动化门禁全部通过，代码层面就绪。D1-D4 所有功能（K3-K6）已完成实现，仅待 V2/V3 真实环境验收。

## 2. 当前范围判断

| 范围 | 当前判断 |
|---|---|
| WP0-WP8 功能实现 | 基本完成，仍需发布环境验收 |
| Alpha 核心闭环 | 已有自动化与 mock 覆盖，缺少干净设备上的桌面 E2E 证据 |
| RAG K1-K2 | 已实现项目扫描、增量目录与本地向量存储 |
| RAG K3 | 已实现 LiteLLM 生产 Provider、BYOK、连接测试和索引身份隔离；真实服务验证暂缓至 V3 |
| RAG K4 | 已实现 `ask_project`、引用校验、上下文限制和 JSON-RPC；真实服务验证暂缓至 V3 |
| RAG K5 | 已实现导入日志索引、失败诊断事件、超时与降级；真实服务验证暂缓至 V3 |
| RAG K6 | 已实现索引状态、Assistant、引用/耗时展示和 Jobs 诊断视图；人工桌面验收暂缓至 V2 |

## 3. 暂缓的验证债务

### V1：CI 基线

状态：`CODE_VERIFIED_PENDING_GITHUB_ENFORCEMENT`

本地代码验证（2026-06-21）：
- ✅ Python 3.11 下 100 tests passed，ruff 零错误
- ✅ TypeScript build + Vitest 7 tests passed
- ⏳ Rust `cargo check` 未在 Windows 本地执行（CI ubuntu-latest 覆盖）

仍需在 GitHub 上完成：
- [ ] 创建受保护的 `external-api-smoke` environment
- [ ] 配置 `DEEPSEEK_API_KEY`、`MESHY_API_KEY`、`OPENAI_API_KEY` 三个 Secret
- [ ] 将 CI jobs（python 3.11/3.12、desktop、rust）设为分支保护必需检查
- [ ] 触发 push 确认全绿 workflow

完成证据：默认分支上的全绿 workflow，且分支保护要求该 workflow 通过。

### V2：干净 Linux 安装包验证

状态：`DEFERRED`

在不预装 Python、`uv` 和项目源码的干净 Linux VM/实机验证：

- AppImage 和 deb 均可安装或启动；
- sidecar 能启动、报告 ready，并在主程序退出后终止；
- 能打开真实 Godot 4 项目；
- ASCII、空格和 Unicode 项目路径均可用；
- Godot executable 自动查找与手动配置行为正确；
- 使用 `meshy_mock` 完成生成、导入检查和 manifest 写入；
- 重启桌面应用后可回放历史 job 事件；
- 日志和诊断文件中不存在明文 API key。

完成证据：记录发行包哈希、发行版版本、Godot 版本、测试步骤和结果。

### V3：真实服务烟雾测试

状态：`DEFERRED`

- 使用测试账号执行 DeepSeek 连接测试和最小请求；
- 使用测试账号执行 Meshy 最小真实工作流；
- 验证限流、认证失败、Provider 超时和安全错误信息；
- 确认真实响应不会进入 stdout JSON-RPC 协议流或泄漏到事件。

完成证据：脱敏测试记录和对应 job/event ID，不保存 Secret 或完整敏感响应。

### V4：Windows 兼容性

状态：`DEFERRED_NON_BLOCKING_ALPHA`

- 在 Windows VM 或实机验证 WebView2；
- 验证盘符、反斜杠、空格、中文路径和长路径；
- 验证 Godot executable 查找；
- 验证 sidecar 打包、启动、取消和进程树终止；
- 验证安装、升级和卸载行为。

Windows 不阻塞当前 Linux alpha，但在 V4 完成前不得发布或标注正式 Windows 构建。

### V5：发布文档与人工验收

状态：`CHECKLIST_IMPLEMENTED_VALIDATION_DEFERRED`

- README 快速开始可在空环境复现；
- BYOK、数据落盘位置、日志脱敏和删除方式有明确说明；
- 提供 Godot 与 Provider 故障排查；
- 维护已知限制和升级/迁移说明；
- 按 `docs/07-v0.1-alpha-implementation-plan.md` 的九项 Exit Criteria 逐项签字。

完成证据：release checklist、已知问题列表和最终人工验收记录。

执行模板、数据位置、已知限制和故障排查已写入
`docs/11-alpha-release-checklist.md`；逐项签字仍需在候选安装包生成后进行。

## 4. 继续开发的执行顺序

验证债务暂缓期间，只推进下列主线。每个阶段完成后保持默认测试不依赖网络或真实 API key。

### D1：生产 Embedding Provider（K3）

状态：`IMPLEMENTED_PENDING_V3`

目标：将确定性 embedding 限定为开发和测试用途，生产环境可使用 BYOK Provider。

任务：

1. 扩展 embedding facade，定义模型、维度、批大小和错误契约；
2. 实现 OpenAI-compatible embedding Provider，复用现有 KeyResolver 和脱敏规则；
3. 增加 Provider 配置、连接测试和 capability 校验；
4. 将知识服务从硬编码 `DeterministicEmbeddingProvider` 改为配置驱动；
5. 保留确定性 Provider 作为离线默认测试替身；
6. 处理 embedding 模型或维度变化，避免混用旧 collection。

验收：离线测试全通过；配置真实 key 时能索引和查询；错误事件不包含 key；模型变化会触发明确的重建流程。

### D2：`ask_project` RAG 问答（K4）

状态：`IMPLEMENTED_PENDING_V3`

目标：在可追溯检索之上生成项目回答，而不是只返回相似片段。

任务：

1. 定义 `KnowledgeAnswer`、citation、latency 和 warning 模型；
2. 组合检索结果和项目上下文，构建受长度限制的 prompt；
3. 通过现有 LiteLLM facade 生成回答；
4. 增加 `ask_project_knowledge` application service 与 JSON-RPC 方法；
5. 强制回答引用来源，并在证据不足时明确返回不确定；
6. 使用 fake LLM 编写完全离线的契约与 sidecar 测试。

验收：回答中的 citation 可映射到真实 chunk；无检索证据时不伪造项目事实；默认测试不访问外网。

### D3：导入诊断集成（K5）

状态：`IMPLEMENTED_PENDING_V3`

目标：Godot 导入失败后自动检索相关项目规则和历史错误，并生成结构化诊断事件。

任务：

1. 将导入错误标准化为可检索的诊断查询；
2. 索引 Godot 导入日志、生成资产 manifest 和 Bridle 诊断文档；
3. 在导入失败分支触发检索，但不覆盖原始错误码；
4. 生成包含建议、引用和耗时的 `knowledge.diagnosis.completed` 事件；
5. 对知识库不可用、空结果和超时采用降级策略。

验收：诊断失败不改变原 job 的终态；建议均带引用；重复执行不会破坏事件顺序或资产状态。

### D4：桌面 Knowledge/Assistant（K6）

状态：`IMPLEMENTED_PENDING_V2`

目标：让用户能够操作索引、查看引用并消费导入诊断结果。

任务：

1. 增加项目索引状态、开始索引和重新索引入口；
2. 增加 Assistant 问答面板；
3. 展示 citation、相似度、来源路径、行号和耗时；
4. 在 Jobs 页面展示 K5 诊断事件；
5. 对长结果做分页或虚拟化，保持 UI 非阻塞；
6. 增加 RPC、state 和 view 层测试。

验收：索引和问答均不阻塞窗口；引用可定位到项目资源；刷新或重启后状态一致。

### D5：Alpha 验证债务清零

D1-D4 完成后暂停功能扩张，依次完成 V1、V2、V3 和 V5。V4 仍可按 Linux alpha 的既定边界后置。全部阻塞项完成后才创建 `v0.1-alpha` release。

### D6：v0.1 MVP 扩展

Alpha 发布后再排期：

1. 验证 LiteLLM 下的 OpenAI/Claude 兼容配置，不分别重写 Provider；配置持久化和桌面编辑已实现，真实 Provider 验证归入 V3；
2. 完成 Windows 支持并建立平台 CI；
3. 评估 Godot 编辑器插件，保持文件系统 + CLI 为稳定后端；
4. 增加发布签名、版本升级和 changelog 自动化。

Tripo、OpenTelemetry、场景模板和更复杂的 Provider 容灾继续归入 v0.2。

## 5. 开发约束

- 不因赶进度降低引用可追溯性或 Secret 脱敏要求；
- 不将真实 API 调用加入默认测试；
- 不在生产路径默认使用确定性 embedding；
- 不把向量库提升为事实源，SQLite 和项目文件仍是可恢复的事实源；
- 不在 V4 完成前宣称 Windows 正式支持；
- 新功能不得扩大 Alpha Exit Criteria，除非先更新计划文档并明确新的发布阻塞项。

## 6. 下一执行项

下一项工作固定为 **D5：Alpha 验证债务清零**。优先实现 V1 CI 基线，再执行需要外部环境的 V2、V3 和 V5。
