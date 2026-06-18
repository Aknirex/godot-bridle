# godot-bridle 需求与现状文档

> **文档版本**：v0.2
> **创建日期**：2026-06-18
> **状态**：草稿，待评审
> **项目代号**：godot-bridle（以下简称 Bridle）


## 一、项目背景

### 1.1 为什么做这个项目

Godot 引擎在 2024-2025 年经历了爆发式增长：Steam 上 Godot 游戏从 2019 年的 56 款增长到 2025 年的 1,229 款；GitHub Stars 从 6 万增长到 13.7 万；编辑器下载量超过 300 万。与此同时，AI 资产生成工具已在多个领域成熟——3D 模型（Meshy、Tripo、Hunyuan3D）、纹理与材质（Meshy Retexture、Polycam）、动画与绑定（Meshy Auto-Rigging、Cascadeur、DeepMotion）——均具备对接游戏引擎的能力。

但问题在于：**这两个世界之间缺少一座桥**。

当前从"AI 生成游戏资产"到"在 Godot 项目里用上它"的工作流高度碎片化——需要手动导出 GLB/FBX、在 Blender 里修复模型、手动导入 Godot、手动配置材质和碰撞体、手写 GDScript 引用。Perforce《2025 State of Game Technology Report》的核心结论至今仍然成立："当前生成式 AI 最大的限制并非生成能力本身，而是缺乏将结果直接转化为可用于生产环境资产的能力。"

**Bridle 的目标就是填上这个缺口。**

### 1.2 项目愿景

> **"让 Godot 开发者用自然语言完成'从概念到可玩资产'的全流程，不被任何单一 AI 供应商锁定。"**

Bridle 不是一个"AI 生成游戏"的平台，也不是一个 Godot 编辑器插件——它是一个**独立运行的 Harness 软件**，与 Godot 编辑器结伴工作。它通过文件系统和 MCP 协议与 Godot 项目交互，负责把 AI 生成的资产——涵盖 3D 模型、纹理材质、动画绑定、游戏代码——**正确、快速、可复用**地导入 Godot 项目，同时为 LLM 提供项目上下文，让 AI 写的代码符合当前项目的版本和风格。用户同时打开 Godot 编辑器和 Bridle，Bridle 在幕后完成 AI 集成与资产管线工作。

### 1.3 核心差异化

| 维度 | Bridle | 现有竞品 |
|---|---|---|
| | **供应商锁定** | 多 LLM + 多资产生成器适配，用户自带 API Key，统一适配器接口一键切换 | 大多绑定单一供应商（如 Meshy MCP 只支持 Meshy） |
| | **切换成本** | 零代码切换：切换 Provider 只需修改配置文件，工作流和模板无需改动 | 更换供应商需重写集成代码 |
| | **资产覆盖** | 3D 模型 + 纹理材质 + 动画绑定三类资产统一管线 | 竞品最多覆盖 1-2 类资产，且不互操作 |
| | **深度集成** | 独立桌面应用，与 Godot 窗口并排运行，通过文件系统 + MCP + CLI 三通道交互 | 多数是 MCP Server 外壳或编辑器插件，不做资产生成导入 |
| | **资产生成导入** | 自动检测 + 修复 + 导入 Godot（核心壁垒） | 竞品只做"生成"，不做"导入后能用" |
| | **技术标准** | Harness 基础设施对标 LangChain/LlamaIndex：流式响应、智能缓存、Provider 容灾、OpenTelemetry 可观测 | 竞品无 Harness 基础设施层，直接裸调 API |
| | **开源协议** | MIT，完全自由 | 部分闭源或有限开源 |
| | **商业模式** | 核心免费 + 模板市场抽成 | SaaS 订阅或闭源付费 |


## 二、现状分析

### 2.1 市场现状

**Godot 生态正在快速成熟：**

- Godot 4.6 已于 2026 年 1 月发布，主打工作流优化、Modern 主题、Jolt Physics 默认、Screen Space Reflections 重写
- Godot 4.7 即将发布，新增 HDR 输出、AreaLight3D 矩形光源、DrawableTexture 等特性
- **Godot 官方 Asset Store 已于 2026 年 5 月上线 Beta**，支持免费和付费资产，创作者可通过官方渠道直接分发插件、工具、模板并获取收入
- 新商店将深度集成到 Godot 4.7 中
- 旧 Asset Library 已标记为 deprecated，将转为只读存档

**这意味着 Bridle 的商业化路径已经打通**——不再是依赖捐赠的"社区玩具"，而是可以通过官方商店销售付费模板和工作流的正经项目。

### 2.2 竞品现状

Godot AI 插件生态在 2026 年已经相当拥挤，但**没有一款产品对准 Bridle 的定位**。

| 项目 | 协议 | 工具数 | 核心能力 | Bridle 的差异 |
|---|---|---|---|---|
| | **GodotIQ** | MIT（22 工具免费）+ $19 全套 | 35 工具 | 空间智能、信号追踪、视觉调试、场景构建 | 聚焦代码/场景编辑，不做资产生成导入 |
| | **godot-ai** | 开源 | ~41 工具，120+ ops | 场景构建、节点编辑、信号连接、UI/材质/动画/粒子 | 生产级 MCP，不做资产生成导入和防锁定 |
| | **godot-mcp-enhanced** | 开源 | 60+ 工具 | 场景读取、脚本读写、截图、GDScript 动态执行、TileMap/AnimationTree/导航系统 | 基于 godot-mcp 增强，无资产生成适配 |
| | **Gamedev AI** | MIT | — | AI 编程助手，内嵌编辑器 | 纯代码辅助 |
| | **Golem-AI** | 开源 | — | 多 LLM 聊天（Ollama/OpenAI/Anthropic/Gemini） | 纯聊天界面，无资产生成 |
| | **Ziva** | 开源中 | — | 全能 AI Agent，支持 ChatGPT/Claude/Gemini | 正在开源，无资产生成导入 |
| | **Meshy MCP (Dokujaa)** | 开源 | — | **已集成 Meshy API**，生成动态场景并直接导入 Godot | **只支持 Meshy**，供应商锁定 |

**关键发现**：

1. **已有竞品做了"Meshy + Godot"集成**（Dokujaa/Godot-MCP）——但这恰恰验证了需求的真实性，同时暴露了单供应商锁定的问题。
2. **Meshy 官方正在做 DCC Bridge**，支持 Godot、Unity、Unreal、Blender、Maya、3ds Max——但 Meshy 的方案是"通用桥接"，不是"深度 Godot 集成"。
3. **没有一款产品同时做到**：(a) 多 LLM 适配 (b) 多资产生成器适配 (c) 深度 Godot 导入修复 (d) 开源 MIT 协议 (e) Harness 级基础设施。

**结论：Bridle 的定位在现有生态中是空白。**

### 2.3 技术现状

**Godot 侧：**
- Godot 项目文件均为文本格式（.tscn / .tres / project.godot），对 AI 友好，外部程序可直接读写
- 已有多个 MCP 实现可供参考（godot-mcp、godot-mcp-enhanced、godot-ai）

**AI 资产生成侧（按资产类型分类）：**

| 资产类型 | 代表服务 | 提供能力 | API 可访问性 |
|---|---|---|---|
| | **3D 模型生成** | Meshy、Tripo、Hunyuan3D、Rodin | Text-to-3D、Image-to-3D | Meshy 提供 MCP；其余提供 REST API |
| | **纹理与材质** | Meshy Retexture、Polycam、ArmorLab | AI 重纹理、PBR 材质生成、照片扫描 | REST API |
| | **动画与绑定** | Meshy Auto-Rigging、Cascadeur、DeepMotion、Plask | 自动骨骼绑定、AI 动作捕捉、物理动画 | REST API / 本地 SDK |

**LLM 侧：**
- Claude API（Anthropic）、GPT API（OpenAI）、Gemini API（Google）均为成熟 REST API
- Ollama 提供本地模型部署能力
- 多家 LLM 已支持 MCP 协议

**Harness 基础设施现状（Bridle 对标参考）：**

| 能力 | LangChain/LlamaIndex 标准 | 当前 Godot AI 生态 | Bridle 目标 |
|---|---|---|---|
| | **统一适配器接口** | ✅ 标准 BaseLLM/BaseChatModel | ❌ 各项目硬编码特定 Provider | ✅ Phase 1 |
| | **流式响应 (Streaming)** | ✅ 原生支持 SSE/WebSocket | ❌ 无人实现 | ✅ Phase 1 |
| | **智能缓存** | ✅ 语义缓存 + TTL | ❌ 无人实现 | ✅ Phase 1 |
| | **Provider 容灾与回退** | ✅ Fallback Chain | ❌ 无人实现 | ✅ Phase 2 |
| | **可观测性** | ✅ OpenTelemetry / LangSmith | ❌ 无人实现 | ✅ Phase 2 |
| | **速率限制与配额管理** | ✅ Token bucket / sliding window | ❌ 无 | ✅ Phase 2 |

**缺口侧（Bridle 的机会）：**
- 没有现成的"AI 生成 GLB → Godot 自动导入 + 修复"的开源实现
- 没有现成的"项目元数据采集 → LLM 上下文注入"的系统化方案
- 没有现成的"多供应商适配器 + 用户 BYOK"的独立 Harness 软件
- 没有现成的"跨资产类型（模型+纹理+动画）统一导入管线"
- Godot AI 生态完全缺乏 Harness 级基础设施（streaming/caching/fallback/observability）


## 三、项目范围

### 3.1 包含（In Scope）

**Phase 1（MVP，3-4 个月）：**

| 模块 | 描述 | 优先级 |
|---|---|---|
| | **Bridle 独立应用骨架** | 独立桌面应用框架，主窗口 UI，项目管理 | P0 |
| | **统一 Provider 适配器接口** | 定义 LLM Provider 和 Asset Provider 的抽象接口（BaseLLMProvider / BaseAssetProvider），新增 Provider 只需实现接口 | P0 |
| | **项目元数据采集器** | 采集 Godot 版本、已装插件、GDScript 风格、项目结构摘要 | P0 |
| | **LLM 上下文桥** | 将元数据格式化为 LLM 可用的上下文 prompt，支持 Claude/GPT；流式响应 | P0 |
| | **Meshy 适配器** | 封装 Meshy MCP/API，支持 Text-to-3D、Image-to-3D、Retexture、Auto-Rigging | P0 |
| | **智能缓存层** | LLM 响应语义缓存 + 资产文件内容缓存，TTL + LRU 淘汰策略 | P0 |
| | **GLB 导入与修复引擎** | 自动检测法线、UV、缩放、材质通道问题并修复，生成 .tres 资源 | P0 |
| | **工作流模板：角色生成** | 端到端模板：输入 prompt → 生成模型 → 自动绑定 → 生成纹理 → 导入 → 配置碰撞体 → 生成引用脚本 | P0 |
| | **用户 API Key 管理** | 环境变量 + 加密存储，BYOK 模式，Provider 级独立配置 | P1 |

**Phase 2（6-9 个月）：**

| 模块 | 描述 | 优先级 |
|---|---|---|
| | **Tripo 适配器** | 接入 Tripo API（实现 BaseAssetProvider 接口） | P1 |
| | **Hunyuan3D 适配器** | 接入 Hunyuan3D（通过 fal.ai 或官方 API） | P1 |
| | **纹理/材质 Provider 适配器** | 接入 Polycam、ArmorLab 等纹理生成服务 | P1 |
| | **动画 Provider 适配器** | 接入 DeepMotion、Plask 等动画生成服务 | P1 |
| | **Provider 容灾与回退链** | 主 Provider 不可用时自动回退到备用 Provider | P1 |
| | **可观测性基础设施** | OpenTelemetry tracing + 结构化日志 + 用量仪表盘 | P1 |
| | **本地 LLM 支持** | 接入 Ollama 本地模型 | P2 |
| | **工作流模板：场景搭建** | 批量生成并摆放多个资产 | P1 |
| | **工作流模板：UI 套件** | 生成 UI 元素和对应脚本 | P2 |
| | **Godot Asset Store 发布** | 上架官方商店 | P1 |

**Phase 3（12-18 个月）：**

| 模块 | 描述 | 优先级 |
|---|---|---|
| | **模板市场** | 社区贡献 + 付费模板销售 | P1 |
| | **速率限制与配额管理系统** | 跨 Provider 的 token bucket + 用户配额可视化 | P1 |
| | **企业版雏形** | 团队协作、私有部署 | P2 |
| | **CI 集成** | 命令行模式，用于自动化构建流水线 | P2 |

### 3.2 不包含（Out of Scope）

- ❌ 不做"AI 一键生成完整游戏"——AI 能力不够 + 玩家反感 + 已有竞品
- ❌ 不做"工作流编排引擎"（多 Agent 协调）——体量太大，Phase 2-3 也不做
- ❌ 不做 AI 模型训练/微调——只做整合，不做模型研发
- ❌ 不做 SaaS 平台——核心是独立桌面应用，不是云端服务
- ❌ 不做 Unity/Unreal 适配——聚焦 Godot


## 四、用户故事与功能需求

### 4.1 核心用户故事

**US1：作为 Godot 独立开发者，我想用自然语言生成一个完整的 3D 角色（模型+纹理+绑定）并直接导入项目**

> 验收标准：
> - 在 Bridle 界面中输入"生成一个低多边形骑士角色"
> - 系统调用 Meshy API 生成模型、纹理、自动绑定
> - 自动导入并修复 GLB（法线、UV、缩放）
> - 自动创建 .tres 材质资源并关联生成纹理
> - 在场景中自动创建节点并配置 CollisionShape
> - 生成一段样板 GDScript 引用该角色
> - 整个过程 < 5 分钟

**US2：作为 Godot 开发者，我想让 AI 写的代码符合我项目的 Godot 版本和插件生态**

> 验收标准：
> - AI 在写代码前能读到项目元数据（Godot 版本、已装插件列表）
> - AI 不会使用当前版本不支持的 API
> - AI 知道项目里已有哪些资源，避免重复生成

**US3：作为 Godot 开发者，我不想被任何单一 AI 供应商锁定，切换成本应为零**

> 验收标准：
> - 可以在设置中切换 LLM 提供商（Claude/GPT/Gemini/Ollama），所有已有模板和工作流无需修改
> - 可以在设置中切换资产生成提供商（Meshy/Tripo/Hunyuan3D），同一工作流自动适配
> - 切换后生成的资产质量应在可接受范围内
> - 所有 API Key 由用户自己管理，Bridle 不存储在后端
> - 当主 Provider 不可用时，自动回退到备用 Provider（Phase 2）

**US4：作为 Godot 开发者，我想贡献新的工作流模板和 Provider 适配器**

> 验收标准：
> - 模板以配置文件 + 脚本定义，与 Bridle 工作流引擎对接
> - 新增 Provider 只需实现 BaseLLMProvider 或 BaseAssetProvider 接口
> - 社区可以通过 PR 贡献模板和适配器
> - 模板可以在 Godot Asset Store 单独发布

**US5：作为 Godot 美术师，我想为现有 3D 模型批量生成多种风格的纹理**

> 验收标准：
> - 选择项目中已有的 GLB 模型
> - 选择纹理风格（写实/卡通/PBR/手绘）
> - 调用纹理生成 Provider 生成并自动关联到模型材质
> - 支持批量处理多个模型
> - 生成结果可在 Godot 中即时预览

### 4.2 功能需求清单

| ID | 需求 | 优先级 | 备注 |
|---|---|---|---|
| | FR1 | Bridle 作为独立桌面应用运行，与 Godot 编辑器并排使用 | P0 | |
| | FR2 | 采集项目 Godot 版本并注入 LLM 上下文 | P0 | |
| | FR3 | 采集已安装插件列表并注入 LLM 上下文 | P0 | |
| | FR4 | 采集项目文件结构摘要并注入 LLM 上下文 | P0 | |
| | FR5 | 支持 Claude API（Anthropic） | P0 | 实现 BaseLLMProvider |
| | FR6 | 支持 OpenAI GPT API | P0 | 实现 BaseLLMProvider |
| | FR7 | 支持 Meshy API 文生3D | P0 | |
| | FR8 | 支持 Meshy API 图生3D | P0 | |
| | FR9 | GLB 文件自动导入 Godot | P0 | |
| | FR10 | 自动检测并修复 GLB 法线方向异常 | P0 | |
| | FR11 | 自动检测并修复 GLB UV 展开问题 | P0 | |
| | FR12 | 自动检测并修复 GLB 缩放比例 | P0 | |
| | FR13 | 自动将 GLB PBR 贴图映射到 Godot StandardMaterial3D | P0 | |
| | FR14 | 自动生成 .tres 材质资源文件 | P0 | |
| | FR15 | 用户 API Key 通过环境变量配置 | P0 | Provider 级独立配置 |
| | FR16 | 用户 API Key 通过项目设置加密存储 | P1 | |
| | FR17 | 支持 Gemini API | P1 | 实现 BaseLLMProvider |
| | FR18 | 支持 Ollama 本地模型 | P2 | 实现 BaseLLMProvider |
| | FR19 | 支持 Tripo API | P1 | 实现 BaseAssetProvider |
| | FR20 | 支持 Hunyuan3D API | P1 | 实现 BaseAssetProvider |
| | FR21 | "角色生成"端到端工作流模板 | P0 | 含模型+纹理+绑定 |
| | FR22 | "场景搭建"端到端工作流模板 | P1 | |
| | FR23 | 错误处理和用户友好提示 | P0 | |
| | FR24 | 应用日志和调试支持 | P1 | |
| | FR25 | Godot Asset Store 发布包 | P1 | |
| | FR26 | 中英文双语 UI | P2 | |
| | FR27 | 统一 LLM Provider 抽象接口（BaseLLMProvider） | P0 | 零代码切换 LLM |
| | FR28 | 统一 Asset Provider 抽象接口（BaseAssetProvider） | P0 | 零代码切换资产服务 |
| | FR29 | LLM 流式响应（Streaming SSE） | P0 | 实时显示生成过程 |
| | FR30 | 智能响应缓存（语义缓存 + TTL + LRU） | P0 | 减少重复 API 调用 |
| | FR31 | 支持 Meshy Retexture（纹理生成） | P0 | |
| | FR32 | 支持 Meshy Auto-Rigging（自动绑定） | P0 | |
| | FR33 | 支持纹理生成 Provider（Polycam 等） | P1 | 实现 BaseAssetProvider |
| | FR34 | 支持动画生成 Provider（DeepMotion 等） | P1 | 实现 BaseAssetProvider |
| | FR35 | Provider 容灾与自动回退链 | P1 | 主 Provider 故障时自动切换 |
| | FR36 | OpenTelemetry 可观测性（tracing + metrics） | P1 | Harness 级基础设施 |


## 五、技术架构（初步）

### 5.1 架构图（概念）

```
┌──────────────────────────┐       ┌──────────────────────────────────────────┐
│   Godot Editor (4.6+)    │       │   Bridle (独立桌面应用)                    │
│                          │       │                                          │
│   用户在此编辑场景和代码   │  MCP  │  ┌────────────────────────────────────┐  │
│                          │◄─────►│  │  主窗口 UI                         │  │
│   project.godot          │  FS   │  │  · 自然语言输入 / 聊天             │  │
│   .tscn / .tres          │◄─────►│  │  · 模板选择与执行                  │  │
│   .gd 脚本               │  CLI  │  │  · 生成进度与预览                  │  │
│                          │       │  │  · 项目设置与 Key 管理             │  │
└──────────────────────────┘       │  └────────────────────────────────────┘  │
                                   │  ┌────────────────────────────────────┐  │
                                   │  │  核心引擎                           │  │
                                   │  │  · 元数据采集器                     │  │
                                   │  │  · 模板执行引擎                     │  │
                                   │  │  · 导入修复引擎                     │  │
                                   │  │  · 资源管理器                       │  │
                                   │  │  · Key 管理                         │  │
                                   │  └────────────────────────────────────┘  │
                                   │  ┌────────────────────────────────────┐  │
                                   │  │  Harness 基础设施层                 │  │
                                   │  │  · 统一 Provider 适配器接口          │  │
                                   │  │  · 流式响应引擎 (SSE)               │  │
                                   │  │  · 智能缓存 (语义 + TTL + LRU)     │  │
                                   │  │  · Provider 容灾与回退链            │  │
                                   │  │  · OpenTelemetry 可观测性           │  │
                                   │  │  · 速率限制与配额管理               │  │
                                   │  └────────────────────────────────────┘  │
                                   │  ┌────────────────────────────────────┐  │
                                   │  │  Provider 适配层                    │  │
                                   │  │  ┌───────── LLM Providers ───────┐ │  │
                                   │  │  │ Claude│GPT│Gemini│Ollama      │ │  │
                                   │  │  └───────────────────────────────┘ │  │
                                   │  │  ┌─────── Asset Providers ────────┐ │  │
                                   │  │  │ 3D: Meshy│Tripo│Hunyuan3D     │ │  │
                                   │  │  │ 纹理: Meshy│Polycam│ArmorLab  │ │  │
                                   │  │  │ 动画: Meshy│DeepMotion│Plask  │ │  │
                                   │  │  └───────────────────────────────┘ │  │
                                   │  └────────────────────────────────────┘  │
                                   └──────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                                   ┌──────────────────────────────────────────┐
                                   │  外部 API（用户自带 Key）                 │
                                   │  Anthropic│OpenAI│Google│Ollama          │
                                   │  Meshy│Tripo│Hunyuan3D                   │
                                   │  Polycam│DeepMotion│Plask               │
                                   └──────────────────────────────────────────┘

  通信通道说明：
  · FS  = 文件系统：Bridle 直接读写 Godot 项目文件（.tscn/.tres/.gd）
  · MCP = Model Context Protocol：通过 Godot MCP Server 实现实时场景交互
  · CLI = Godot --script：通过命令行调用 Godot 执行特定操作
```

### 5.2 技术选型（初步）

| 组件 | 选型 | 理由 |
|---|---|---|
| | **主应用程序** | Python 3.11+（桌面：Tauri v2 + Python sidecar） | Tauri 是 2026 年桌面 AI 工具首选框架——2-10MB vs Electron 80-244MB，GitHub 55% YoY 增长；Cody/AI 工具已迁移至 Tauri |
| | **Godot 通信** | 文件系统读写 + MCP 协议 + Godot --script CLI | 三通道互补：FS 做资产读写，MCP 做实时交互，CLI 做批量操作 |
| | **LLM 通信** | REST API / MCP + SSE Streaming | 标准协议；SSE 实现实时流式响应 |
| | **资产生成通信** | REST API / MCP | 3D/纹理/动画三类资产统一通过 BaseAssetProvider 抽象 |
| | **GLB 处理** | Python (trimesh/pyglet) 或调用 Godot CLI | Python 有成熟的 3D 处理库；复杂修复可委托 Godot 引擎处理 |
| | **流式响应** | SSE (Server-Sent Events) / WebSocket | 行业标准；与 LangChain streaming 接口对齐 |
| | **智能缓存** | diskcache（MVP）→ GPTCache（Phase 2） | diskcache 零依赖、10K reads/s；GPTCache 提供真正的 embedding 语义匹配，成本可降 73% |
| | **可观测性** | OpenTelemetry SDK + structlog，遵循 gen_ai.* 语义约定 | 对标 LangSmith + Mirascope 原生 OTel 集成模式；tracing + metrics + logging 三位一体 |
| | **Provider 容灾** | 回退链 (Fallback Chain) + 断路器 (Circuit Breaker) | 主 Provider 不可用时自动切换，避免雪崩 |
| | **存储** | 项目本地文件 + Bridle 配置文件 | 无需外部数据库，所有配置跟随项目或用户目录 |
| | **许可证** | MIT | Godot 社区最主流，商业友好 |

### 5.3 关键设计决策

1. **统一适配器接口**：所有 LLM Provider 实现 `BaseLLMProvider`（统一 `chat()`, `stream_chat()` 方法）；所有 Asset Provider 实现 `BaseAssetProvider`（统一 `generate_3d()`, `generate_texture()`, `generate_rig()` 方法）。新增供应商只需实现对应接口，上层工作流代码零改动。
2. **BYOK 优先**：用户自带 API Key，Bridle 不承担 API 成本，不存储用户密钥在云端。每个 Provider 独立配置 Key，支持环境变量和加密存储两种方式。
3. **本地优先**：核心功能在本地运行，不依赖云端服务（除 API 调用外）。缓存、元数据、日志全部本地存储。
4. **流式优先 (Streaming-First)**：所有 LLM 交互默认使用 SSE 流式响应，实时展示生成过程。非流式作为兼容回退。
5. **缓存优先 (Cache-First)**：所有 LLM 响应进行语义缓存，所有资产文件进行内容哈希缓存。相同请求命中缓存时零 API 调用、零延迟。
6. **三通道通信**：文件系统（资产读写）+ MCP（实时场景交互）+ Godot CLI（批量操作），根据任务类型自动选择最优通道。
7. **模板化**：工作流以模板定义，社区可贡献，可上架商店销售。模板基于统一 Provider 接口编写，天然跨 Provider 可移植。
8. **持续对标**：开发全程持续追踪 GitHub 上 LangChain、LlamaIndex、Mirascope、CrewAI、Dify、Flowise 等主流 Harness/LLMOps 项目的架构演进，以及 Godot AI 生态中新出现的 MCP/插件项目，定期评估吸收其最佳实践，确保 Bridle 的 Harness 基础设施始终保持行业领先水平。

### 5.4 Harness 基础设施架构（对标行业标准）

Bridle 的 Harness 基础设施层对标 LangChain/LlamaIndex 的企业级标准，在 Godot AI 生态中属首创：

```
┌─────────────────────────────────────────────────────────────┐
│                    Harness 基础设施层                         │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Provider Hub │  │ Stream Engine│  │  Cache Manager   │  │
│  │              │  │              │  │                  │  │
│  │ · 注册/发现   │  │ · SSE 流     │  │ · 语义缓存       │  │
│  │ · 健康检查    │  │ · 背压控制   │  │ · 内容哈希缓存   │  │
│  │ · 负载均衡    │  │ · 断线重连   │  │ · TTL + LRU     │  │
│  │ · 回退链      │  │ · 分块合并   │  │ · 预热策略       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Rate Limiter │  │  Circuit Br. │  │  Telemetry       │  │
│  │              │  │              │  │                  │  │
│  │ · Token桶    │  │ · 熔断检测   │  │ · Tracing (OTLP) │  │
│  │ · 滑动窗口   │  │ · 半开试探   │  │ · Metrics (普罗) │  │
│  │ · 配额可视化 │  │ · 自动恢复   │  │ · Logging (结构化)│  │
│  │ · 跨Provider │  │ · 降级策略   │  │ · Dashboard      │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**各组件对标说明：**

| 组件 | 对标标准 | Bridle 实现策略 |
|---|---|---|
| | **Provider Hub** | LangChain `BaseChatModel` + `model_kwargs` | 统一 `BaseLLMProvider` / `BaseAssetProvider` 抽象；Provider Registry 支持运行时注册和发现 |
| | **Stream Engine** | LangChain `astream_events()` / OpenAI SSE | 基于 SSE 标准；支持背压控制避免内存溢出；断线自动重连 |
| | **Cache Manager** | LangChain `InMemoryCache` / GPTCache | 语义缓存用 embedding 相似度匹配；资产文件用 SHA256 内容哈希；TTL 可配置 |
| | **Rate Limiter** | OpenAI `RateLimitError` 处理模式 | Token bucket 算法；跨 Provider 统一配额视图；用户可配置每 Provider 限额 |
| | **Circuit Breaker** | Netflix Hystrix 模式 | 连续失败 N 次熔断；半开状态试探恢复；自动回退到备用 Provider |
| | **Telemetry** | LangSmith / OpenTelemetry 标准 | OTLP 导出；span 级 LLM 调用追踪；Prometheus metrics 端点；结构化 JSON 日志 |


## 六、版本规划

### 6.1 v0.1 - MVP（目标：2026 年 10 月）

**核心交付**：
- Bridle 独立桌面应用（主窗口 UI + 项目管理）
- 统一 Provider 适配器接口（BaseLLMProvider + BaseAssetProvider）
- 项目元数据采集器（版本 + 插件 + 文件结构）
- Claude API 适配器 + GPT API 适配器
- Meshy API 适配器（文生3D + 图生3D + Retexture + Auto-Rigging）
- 流式响应引擎（SSE）
- 智能缓存层（语义缓存 + 内容哈希缓存）
- GLB 导入与自动修复引擎（法线、UV、缩放、材质映射）
- "角色生成"工作流模板（模型+纹理+绑定全流程）
- 用户 API Key 环境变量配置（Provider 级独立）
- 基础错误处理和结构化日志

**发布渠道**：
- GitHub（开源，MIT）
- Godot Asset Store（免费）

**成功标准**：
- GitHub Stars > 200
- Asset Store 下载 > 500
- 无重大 Bug 的稳定版本
- LLM Provider 切换：修改 1 行配置即可生效
- 缓存命中率 > 30%（减少 API 调用成本）

### 6.2 v0.2 - 生态扩展（目标：2027 年 Q1）

**新增**：
- Gemini API 适配器
- Tripo API 适配器
- 纹理 Provider 适配器（Polycam 等）
- 动画 Provider 适配器（DeepMotion 等）
- Provider 容灾与自动回退链
- 断路器（Circuit Breaker）
- OpenTelemetry 可观测性（tracing + metrics）
- "场景搭建"工作流模板
- 用户 API Key 加密存储（Bridle 配置文件）
- 中文 UI

### 6.3 v1.0 - 正式版（目标：2027 年 Q2）

**新增**：
- Ollama 本地模型支持
- Hunyuan3D 适配器
- 速率限制与配额管理系统
- "UI 套件"工作流模板
- Godot Asset Store 付费模板上架
- 用量仪表盘（Dashboard）
- 完整文档和教程
- 社区贡献指南

### 6.4 后续方向（v1.0+）

- 模板市场（社区贡献 + 付费销售）
- 企业版（团队协作、私有部署）
- CI 命令行模式
- Provider 性能基准测试与推荐引擎


## 七、资源需求

### 7.1 人力资源

| 角色 | 人数 | 时间 | 职责 |
|---|---|---|---|
| | **核心开发者** | 1-2 人 | 3-4 个月（MVP） | Bridle 应用开发、Harness 基础设施、Provider 适配、导入引擎 |
| | **技术文档** | 0.5 人 | 持续 | API 文档、Provider 开发指南、用户教程、贡献指南 |
| | **社区运营** | 0.5 人 | 持续 | Discord、Issue 管理、PR 审核、Provider 生态拓展 |

**总工作量估算**：10-14 人月（MVP，含 Harness 基础设施）

### 7.2 技术依赖

- Godot 4.6+ 引擎（用户侧）
- Python 3.11+（主应用开发）
- OpenTelemetry SDK（可观测性）
- Meshy API 账号（测试用）
- Claude/GPT API 账号（测试用）
- Polycam / DeepMotion API 账号（Phase 2 测试用）

### 7.3 资金需求（MVP）

| 项目 | 估算 | 备注 |
|---|---|---|
| | 开发者时间（机会成本） | — | 开源贡献 |
| | API 测试费用 | $50-100/月 | Meshy + Claude 测试用量 |
| | 域名和基础设施 | $20/月 | GitHub Pages 文档、Discord |
| | **合计** | **$70-120/月** | MVP 阶段 |


## 八、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| | **Meshy 官方推出深度 Godot 插件** | 中 | 高 | 差异化在多供应商适配 + 防锁定 + 跨资产类型覆盖，不只是 Meshy |
| | **Godot 项目文件格式变动** | 低 | 中 | 文本格式稳定性高；通过 MCP 和 CLI 多通道兜底 |
| | **GLB 导入修复过于复杂** | 中 | 高 | MVP 只做最常见问题的自动修复，复杂情况提供手动指南 |
| | **Harness 基础设施复杂度超预期** | 中 | 中 | 参考 LangChain 成熟架构；MVP 仅实现核心（统一接口+流式+缓存），容灾/可观测推迟到 Phase 2 |
| | **AI 资产生成服务质量不稳定** | 中 | 中 | Provider 容灾回退链确保可用性；缓存层减少重复调用 |
| | **社区贡献不足** | 中 | 中 | 降低贡献门槛（统一接口只需实现一个类），提供清晰模板和文档 |
| | **Godot Asset Store 付费功能延期** | 低 | 低 | 付费模板作为 Phase 3 目标，不阻塞 MVP |
| | **竞品先发布类似产品** | 中 | 中 | 快速迭代 + Harness 基础设施壁垒（竞品短期难以复制） |


## 九、下一步行动

### 9.1 立即行动（本周）

1. **创建 GitHub 仓库**：`godot-bridle`，MIT 协议
2. **搭建项目骨架**：Python 项目结构（Poetry/pnpm）+ BaseLLMProvider / BaseAssetProvider 接口定义
3. **创建 Discord 服务器**：社区沟通渠道
4. **撰写项目 README**：愿景、路线图、Provider 开发贡献指南

### 9.2 短期行动（本月）

1. **实现 BaseLLMProvider 接口 + Claude 适配器原型**：验证统一接口 + 流式响应
2. **实现 BaseAssetProvider 接口 + Meshy 适配器原型**：验证 3D + 纹理 + 绑定全流程
3. **实现智能缓存层原型**：验证语义缓存 + 内容哈希缓存命中率
4. **实现 GLB 导入原型**：验证通过文件系统写入 Godot 项目 + 基础修复
5. **发布 v0.1-alpha**：内部测试

### 9.3 需要决策的问题

1. **主应用选 Python 桌面框架还是 Electron/Tauri？** → 建议 MVP 先用 Python（PySide 或 Web UI），后期根据用户体验反馈决定是否迁移
2. **缓存后端选 SQLite 还是 Redis？** → 建议 MVP 用 SQLite/diskcache（零外部依赖），Phase 2 可选 Redis 提升性能
3. **GLB 处理用 Python 库还是委托 Godot CLI？** → 建议先用 Python trimesh 快速验证，复杂修复委托 Godot --script 处理
4. **第一个支持的 3D 生成器选 Meshy 还是 Tripo？** → 建议 Meshy（MCP 已就绪，且覆盖 3D+纹理+绑定三类资产）
5. **是否参与 Google Summer of Code 或类似项目？** → 建议 v0.2 后考虑


## 十、附录

### A. 参考资料

1. 可行性决策报告《Godot Harness 可行性决策报告》（2026-06-18）
2. Clay John (Godot Foundation) ——《Godot 使用量与引擎增长》（2026-05-06）
3. Godot 4.6 Release Notes（2026-01-26）
4. Godot 4.7 Dev Snapshots（2026-03-26 至 2026-06-11）
5. Godot Asset Store 官方公告（2026-05-22）
6. Meshy API 文档（docs.meshy.ai）
7. LangChain Documentation（python.langchain.com）
8. LlamaIndex Documentation（docs.llamaindex.ai）
9. OpenTelemetry Specification（opentelemetry.io）
10. Mirascope —— Typesafe Pythonic LLM Abstractions（github.com/Mirascope/mirascope）
11. GPTCache —— Semantic Cache for LLM Responses（github.com/zilliztech/GPTCache）
12. Tauri vs Electron 2026 Benchmark —— Tech Insider（tech-insider.org）
13. GodotIQ —— Asset Library（2026-03-16）
14. godot-ai —— PyPI（2026）
15. godot-mcp-enhanced —— npm（2026-06-09）

### B. 术语表

| 术语 | 解释 |
|---|---|
| | **Harness** | 整合多个 AI 工具和 API 的编排层/适配层，提供缓存、容灾、可观测等企业级基础设施 |
| | **MCP** | Model Context Protocol，AI 模型与工具交互的协议 |
| | **BYOK** | Bring Your Own Key，用户自带 API 密钥 |
| | **Provider** | AI 服务提供商（LLM 或资产生成），通过统一适配器接口接入 Bridle |
| | **BaseLLMProvider** | LLM Provider 统一抽象接口，定义 `chat()` 和 `stream_chat()` 标准方法 |
| | **BaseAssetProvider** | 资产 Provider 统一抽象接口，定义 `generate_3d()`、`generate_texture()`、`generate_rig()` 标准方法 |
| | **GLB** | glTF 二进制格式，Godot 原生支持的 3D 模型格式 |
| | **.tscn** | Godot 场景文件（文本格式） |
| | **.tres** | Godot 资源文件（文本格式） |
| | **FS** | File System，文件系统直读写 |
| | **CLI** | Command Line Interface，命令行接口 |
| | **SSE** | Server-Sent Events，流式响应协议 |
| | **TTL** | Time To Live，缓存过期时间 |
| | **LRU** | Least Recently Used，缓存淘汰策略 |
| | **Circuit Breaker** | 断路器模式，连续失败后自动熔断以保护系统稳定性 |
