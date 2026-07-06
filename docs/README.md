# Bridle 文档索引

本文档目录已经按“当前主线”和“历史资料”重新整理。当前开发重心是功能管线验证，不再把界面完善或 alpha 发布包装作为主驱动力。

## 当前主线

| 文档 | 用途 |
|---|---|
| [`12-functional-pipeline-reset-and-roadmap.md`](12-functional-pipeline-reset-and-roadmap.md) | 当前评估、产品重置、下一步开发计划 |
| [`02-requirements-analysis.md`](02-requirements-analysis.md) | 原始需求分析，仍保留核心问题和用户场景 |
| [`05-system-design.md`](05-system-design.md) | 系统设计背景 |
| [`06-detailed-design-core-contracts.md`](06-detailed-design-core-contracts.md) | 核心契约设计背景 |
| [`08-rag-vector-knowledge-base.md`](08-rag-vector-knowledge-base.md) | 项目上下文、检索和诊断能力设计 |

## 实现与验证资料

| 文档 | 状态 |
|---|---|
| [`07-v0.1-alpha-implementation-plan.md`](07-v0.1-alpha-implementation-plan.md) | 已实现计划，作为代码映射参考 |
| [`09-alpha-development-and-packaging.md`](09-alpha-development-and-packaging.md) | 打包和开发说明，非当前产品路线 |
| [`11-alpha-release-checklist.md`](11-alpha-release-checklist.md) | alpha 发布检查表，暂停作为主线 |
| [`validation/`](validation/) | 脱敏验证记录模板 |

## 已归档

旧的“验证债务与后续开发计划”已移动到 [`archive/10-validation-debt-and-next-development-plan.md`](archive/10-validation-debt-and-next-development-plan.md)。该文档仍可用于理解 alpha 收口历史，但不再定义下一步开发优先级。

## 文档维护规则

- 新路线和产品判断优先写入 `12-functional-pipeline-reset-and-roadmap.md`。
- 只把经过验证的实现状态写入 README 或发布检查表。
- UI 相关工作必须服务于管线可操作性、可诊断性和可复现性，不单独作为路线目标。
- Provider、Godot 导入、资产请求格式和工作流协议的变化必须同步更新契约文档。
