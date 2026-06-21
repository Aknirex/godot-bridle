# v0.1-alpha 发布检查表

本文件用于执行最终发布验收。没有证据的项目不得勾选；自动化测试通过不能替代干净设备上的桌面验收。

## 1. 构建身份

- [ ] 记录 commit SHA、版本号和构建日期；
- [ ] 工作树无未预期修改；
- [ ] Python、Node、Rust 和 Godot 版本已记录；
- [ ] AppImage、deb 和 sidecar 的 SHA-256 已记录；
- [ ] release notes 包含已知限制和兼容平台。

## 2. 自动化门禁

- [ ] GitHub Actions 的 Python 3.11/3.12 jobs 通过；
- [ ] Ruff 和默认 pytest 通过，真实 API 测试未在默认 job 执行；
- [ ] Vitest 和前端生产构建通过；
- [ ] `cargo check --locked` 通过；
- [ ] CI jobs 已配置为受保护分支的必需检查；
- [ ] `external-api-smoke` environment 需要人工批准且 Secret 不对普通 PR 开放。

## 3. 干净 Linux 验收

- [ ] 在没有 Python、`uv` 和项目源码的环境启动 AppImage；
- [ ] 安装并启动 deb；
- [ ] sidecar ready、退出和异常重启行为正确；
- [ ] ASCII、空格和 Unicode Godot 项目路径通过；
- [ ] 打开真实 Godot 4 项目并识别版本与 addons；
- [ ] `meshy_mock` 完整工作流成功并写入 `bridle_asset.json`；
- [ ] Godot executable 自动查找失败时提供安全错误，手动路径可用；
- [ ] 应用重启后 job/event、Provider metadata 和知识索引状态仍存在；
- [ ] AppImage/deb 行为差异已记录。

## 4. 真实 Provider 验收

- [ ] DeepSeek 最小 chat smoke test 通过；
- [ ] OpenAI embedding smoke test 通过；
- [ ] Meshy 最小真实生成工作流通过；
- [ ] 认证失败、限流、超时和 Provider 错误均显示脱敏详情；
- [ ] 导入失败诊断能返回真实引用，诊断失败不改变原 job 错误；
- [ ] stdout 仅包含 JSON Lines 协议消息。

## 5. Alpha Exit Criteria

- [ ] 桌面应用可打开真实 Godot 项目；
- [ ] DeepSeek 和 Meshy BYOK 配置与连接测试可用；
- [ ] 提交 workflow 后立即返回 `job_id`，UI 保持响应；
- [ ] 生成、下载、GLB 检测和 Godot 导入全部在后台执行；
- [ ] 晚订阅可以从 SQLite 回放完整 job 历史；
- [ ] 成功后项目内存在生成资产 manifest；
- [ ] 失败时显示统一错误码和脱敏 `safe_details`；
- [ ] 默认测试和提供 key 后的 smoke tests 通过；
- [ ] 日志、事件和诊断导出中没有明文 API key。

## 6. 数据与 Secret

桌面应用将持久状态写入 Tauri 为 `dev.bridle.godot` 分配的 app-data 目录：

- `sidecar.sqlite3`：job、event、Provider metadata、benchmark 和知识目录；
- `knowledge-vectors/`：按项目和 embedding 配置隔离的可重建向量索引；
- Godot 项目内的 `res://bridle/generated/`：生成资产、manifest 和导入日志。

独立运行 `bridle sidecar` 时应显式传 `--db <path>`；未传参数仅适合临时开发会话。

API key 只通过 `api_key_env` 指向的环境变量读取，不写入 TOML、SQLite、事件或 manifest。删除本地状态前必须先退出桌面应用；删除 app-data 会清除 job 历史和知识索引，但不会删除 Godot 项目中的生成资产。

## 7. 已知限制

- Windows 尚未经过 VM/实机验证，不发布正式 Windows 构建；
- macOS 尚无签名、公证和实机验收；
- Alpha 只承诺 Linux AppImage/deb 候选包；
- 知识回答依赖已配置的生产 embedding 与 LLM Provider；
- 向量索引可重建，不作为项目事实源；
- GLB 流程只做检测、基础准备和 Godot 导入验证，不保证自动修复所有模型问题；
- Jobs 页面当前只展示一个活动任务，不是完整多任务管理器。

## 8. 故障排查

### Sidecar 无法启动

确认安装包包含 `bridle-sidecar`、app-data 可写，并检查 stderr。stdout 被协议独占，不应写普通日志。

### Provider 显示 missing_key

确认环境变量名称与 Provider 的 `api_key_env` 一致，并从同一桌面进程环境启动应用。错误报告中不得粘贴完整 key。

### Godot 导入失败

检查生成资产目录下的 `logs/godot_import_stdout.log` 和 `logs/godot_import_stderr.log`，同时查看 Jobs 中的知识诊断引用。诊断建议不能替代原始退出码和日志。

### 知识索引不可用

先验证 embedding Provider 连接，再重新索引项目。切换 embedding 模型会使用新的向量 collection 并强制重新索引。

## 9. 发布决定

- [ ] V1、V2、V3 和 V5 的证据完整；
- [ ] 所有阻塞问题已关闭或明确从 Alpha 范围移除；
- [ ] 发布负责人批准创建 `v0.1-alpha` tag 和 GitHub Release。
