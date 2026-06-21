# V4 Windows 证据

- 状态：`CANDIDATE_BUILD_READY_PENDING_CLEAN_VM`
- commit：`0aa78ecbc81b0e45e18830b9771ea31e6788c4b2`
- workflow run：`27896180266`，Windows job 成功并通过 packaged-sidecar health check
- artifact：`godot-bridle-windows-0aa78ecbc81b0e45e18830b9771ea31e6788c4b2`
- NSIS / sidecar SHA-256：见 artifact 内 `SHA256SUMS-windows.txt`，VM 下载后复核
- Windows 11 版本、架构、WebView2、Godot 版本：`PENDING`
- 安装、覆盖升级、卸载：`PENDING`
- 盘符 / 反斜杠 / 空格 / 中文 / 长路径：`PENDING`
- Godot 自动查找与手动配置：`PENDING`
- sidecar 启动、取消、窗口退出后的进程树：`PENDING`
- 验证人、时间、截图/日志的脱敏位置：`PENDING`

## 当前 Windows 主机预检（不替代干净 VM）

- 2026-06-21：`cargo check --locked` 与本地 NSIS 构建成功。
- PyInstaller sidecar 修复 tiktoken plugin 收集后通过 JSON-RPC health check。
- 观察到 packaged sidecar ready/health 用时约 93–116 秒；V4 验收必须复测并将该启动时延作为
  发布风险处理，未确认可接受前本记录保持 `PENDING`。
