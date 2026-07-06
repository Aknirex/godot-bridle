# 功能管线重置与下一步路线图

> 最后更新：2026-07-06  
> 当前判断：项目应从“桌面 alpha/UI 收口”切回“重功能工具链验证”。

## 1. 重置结论

Bridle 的核心价值不是漂亮界面，也不是再做一个单供应商 AI 资产生成入口。它要补齐三段系统之间的空隙：

1. 需求文档、设计说明、Agent 输出；
2. 3D 模型、纹理、绑定、动画等资产生成供应商；
3. Godot 项目中的可导入、可追踪、可复用资产。

下一阶段必须优先验证一条可复现的功能闭环：

```text
需求文档 -> 资产生产请求 -> Provider 执行 -> 资产下载/检测 -> Godot 导入 -> manifest/诊断/复用记录
```

界面只保留提交、观察、诊断和复现这条链路所需的最小入口。任何纯展示、美化、多页面扩展都延后。

## 2. 现状评估

### 已有可复用基础

| 模块 | 现状 | 可复用价值 |
|---|---|---|
| Job/事件/SQLite | 已有异步任务、事件回放、状态存储 | 适合作为长资产任务的事实记录层 |
| Provider 层 | 已有 LiteLLM、Embedding、Meshy/mock 和 capability 基础 | 可继续抽象成资产生产请求执行器 |
| Godot 集成 | 已有项目检测、生成目录、GLB 检测、Godot CLI 导入检查 | 可作为导入验证底座 |
| RAG/知识库 | 已有项目扫描、引用问答、导入失败诊断 | 可用于需求理解、项目上下文注入和失败解释 |
| Tauri shell | 已能承载 sidecar 与事件流 | 只应作为工具控制台，不应主导产品方向 |

### 关键缺口

| 缺口 | 影响 |
|---|---|
| 没有“需求文档解析到资产清单”的中间表示 | 无法从设计文档稳定生成可执行资产任务 |
| 资产生产请求仍偏向单一角色 prompt | 难以表达模型、材质、风格、LOD、尺寸、碰撞、命名、Godot 目标路径等生产约束 |
| Provider 能力到请求字段的映射不够明确 | 无法证明多供应商可替换，只是代码层 facade |
| Godot 导入只做基础准备和检查 | 核心壁垒“导入后能用”尚未充分验证 |
| 缺少工作流验收样例项目 | 无法比较每轮修改是否让真实生产链路更稳定 |
| 文档主线仍停留在 alpha 发布和 UI 验收 | 容易继续投入到低价值表层体验 |

## 3. 新的 P0 目标

P0 不再定义为“发布 alpha 桌面应用”，而是定义为“验证标准化资产生产管线是否成立”。

### P0 验收标准

1. 输入一份带 Bridle 标记块或由 LLM/Agent 预整理出的需求文档，系统能提取结构化 `AssetBrief` 列表；完全自由格式文档进入 LLM-assisted parsing 验证，不作为 deterministic parser 的证明范围。
2. 每个 `AssetBrief` 能转换为可审计的 `AssetProductionRequest`，包含目标用途、风格、尺寸、格式、Godot 路径、Provider capability 需求和验收条件。
3. 工作流不直接依赖 Meshy 字段，而是通过 capability 匹配生成 Provider-specific request。
4. 生成结果写入 `res://bridle/generated/<asset_id>/`，并产生 `bridle_asset.json`、原始请求、Provider 响应摘要、检测报告和导入日志。
5. Godot 导入失败时，系统能给出结构化原因、引用日志和下一步处理建议。
6. 至少有一个样例 Godot 项目和一份样例需求文档可离线跑通 mock E2E。
7. 真实 Meshy smoke test 只作为人工验证，不进入默认测试。

## 4. 下一步开发计划

### F1：需求到资产清单的中间表示

产出：`AssetBrief`、`AssetProductionRequest`、`AssetAcceptanceCriteria` 模型和 JSON schema。

边界：F1 的 deterministic parser 不是自由文本理解器。它只负责解析受约束输入，例如 Markdown front matter、`bridle-assets` fenced block、表格或 LLM/Agent 已输出的 JSON。真实自由格式需求文档必须通过 LLM-assisted parser 或人工确认步骤转成受约束格式，再进入确定性校验。

模型关系：`AssetProductionRequest` 是上游“生产意图/计划”模型，描述要做什么、为什么做、落到 Godot 哪里、用什么验收。现有 `AssetGenerationRequest` 是下游 Provider 执行模型，描述发给 text-to-3d Provider 的最小请求。短期内不替换 `AssetGenerationRequest`，而是新增 adapter：`AssetProductionRequest -> AssetGenerationRequest`。`character_workflow.py` 可先保留单 prompt 入口，并增加结构化请求入口作为新路径。

`AssetAcceptanceCriteria` 最小字段：

| 字段 | 含义 |
|---|---|
| `required_format` | 期望源资产格式，P0 固定或默认 `glb` |
| `godot_import_required` | 是否必须执行 Godot import check |
| `target_res_path` | 期望写入或引用的 `res://` 路径前缀 |
| `scale_hint` | 资产尺寸/比例提示，先作为文本或枚举，不做自动修复承诺 |
| `style_tags` | 用于校验 prompt/manifest 是否保留风格要求 |
| `must_include` | 必须包含的语义元素，例如 “sword”、“low-poly” |
| `must_not_include` | 禁止出现的语义元素或风格 |
| `max_provider_attempts` | Provider 层最多尝试次数 |
| `manual_review_required` | 是否需要人工验收标记，默认 true |

任务：

1. 定义受约束需求输入格式，优先支持 Markdown 中的 `bridle-assets` JSON/YAML fenced block 和简单表格。
2. 定义资产类型、目标用途、风格、规模、技术约束、Godot 目标路径、优先级和依赖关系。
3. 实现离线 deterministic parser，用规则和 schema 校验受约束输入，不声称能理解任意自由文本。
4. 定义 LLM-assisted parser 接口：输入自由文本，输出受约束 `AssetBrief` JSON，再由 deterministic validator 做最终校验；默认测试使用 fake LLM。

验收：受约束样例需求文档能稳定输出相同资产清单；自由格式样例必须经过 fake LLM 转换后再通过 schema；字段缺失时返回可修正的 validation error。

### F2：资产请求到 Provider capability 的匹配

产出：对现有 `ProviderResolver` 的扩展方案、request adapter contract tests。

关系：F2 不新建并行 resolver。现有 `bridle.providers.resolver.ProviderResolver` 已负责 `ProviderCapability -> ProviderConfig` 的选择，F2 应复用它，并只补充两层能力：从 `AssetProductionRequest` 推导 required capabilities；从选中的 `ProviderConfig` 和 neutral execution plan 生成具体 `AssetGenerationRequest`。

任务：

1. 明确 text-to-3d、image-to-3d、retexture、rigging、animation、embedding、chat 等 capability 的输入输出契约。
2. 将 `AssetProductionRequest` 映射为 required capabilities，并交给现有 `ProviderResolver.resolve()` 选择 Provider。
3. 将 `AssetProductionRequest` 映射到 Provider-neutral execution plan。
4. Meshy adapter 只负责把 neutral plan 翻译为现有 `AssetGenerationRequest` 和 Meshy provider options。
5. 能力不足时返回结构化错误，而不是在工作流中硬编码分支。

验收：mock Provider 和 Meshy Provider 通过同一组契约测试；Provider 选择路径覆盖 `ProviderResolver`；Provider 切换不改变上层工作流代码。

### F3：Godot 导入包规范

产出：`bridle_asset.json` v2、请求快照、检测报告、导入日志目录规范。

任务：

1. 扩展 manifest，记录原始需求、生产请求、Provider、生成文件、检测结果、Godot 路径和复现信息。
2. 为每个资产生成稳定目录结构：`source/`、`godot/`、`logs/`、`reports/`。
3. 将 GLB 检测报告、Godot CLI 输出和诊断事件绑定到 asset_id。
4. 建立 manifest schema 版本，避免后续格式变更不可迁移。

验收：删除 SQLite 后只要求能通过项目目录中的 manifest 重建“生成资产索引”和资产详情视图；不要求恢复 job 运行状态、历史事件流、knowledge collection、embedding index 或 Provider health 记录。这些仍由 SQLite/app-data 管理，必要时可从 manifest 重新索引，但不属于 F3 验收。

### F4：样例项目和端到端验收

产出：离线 fixture Godot 项目、样例需求文档、mock E2E 测试。

任务：

1. 新建最小 Godot fixture，包含项目配置、目标目录和预期生成路径。
2. 编写样例需求，例如“低多边形角色 + 武器 + 可交互道具”。
3. 使用 mock Provider 生成本地 GLB fixture，跑通解析、计划、执行、导入准备和 manifest 写入。
4. 增加回归测试，防止后续 UI 或 Provider 改动破坏核心链路。

验收：`uv run pytest` 默认离线通过完整功能管线测试。

### F5：最小工具控制台

产出：围绕功能链路的最小 UI/CLI 操作路径。

任务：

1. CLI 先提供 `plan-assets`、`run-asset-plan`、`inspect-asset` 命令。
2. 桌面端只展示需求输入、计划预览、执行进度、manifest 和诊断。
3. 不做美化优先事项，不新增与功能链路无关页面。

验收：用户能看懂每个资产为何生成、发给哪个 Provider、落到 Godot 哪里、失败时如何处理。

## 5. 暂停事项

以下事项暂停，直到 F1-F4 证明管线成立：

- 桌面视觉设计、美化和非必要页面；
- Godot Asset Store 发布准备；
- Windows/macOS 打包投入；
- 新 Provider 扩张；
- 模板市场、商业化和多 Agent 编排；
- 与核心管线无关的 RAG UI 扩展。

## 6. 文档归档决定

`docs/10-validation-debt-and-next-development-plan.md` 已归档到 `docs/archive/`。该文档描述的是上一阶段 alpha 发布收口计划，不再作为当前开发顺序依据。

`docs/07-v0.1-alpha-implementation-plan.md`、`docs/09-alpha-development-and-packaging.md`、`docs/11-alpha-release-checklist.md` 暂时保留在原位置，因为它们仍提供实现映射、打包说明和检查表；但当前路线以本文档为准。

## 7. 立即执行项

1. 实现 `AssetBrief`、`AssetProductionRequest`、`AssetAcceptanceCriteria` 模型和 JSON schema。
2. 增加受约束样例需求文档 fixture、自由格式经 fake LLM 转换 fixture 和解析/校验测试。
3. 实现 `AssetProductionRequest -> AssetGenerationRequest` adapter，不替换现有 `AssetGenerationRequest`。
4. 扩展 `ProviderResolver` 使用路径，确保资产生产请求先推导 capability，再进入已有 resolver。
5. 改造角色工作流入口，使其增加结构化资产请求路径，同时保留现有单 prompt 兼容入口。
6. 扩展 manifest，保存请求快照和检测报告。
7. 建立 mock E2E，验证“需求文档到 Godot 生成目录”的离线闭环。
