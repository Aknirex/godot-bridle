# V4 Windows 证据

- 状态：`CANDIDATE_BUILD_READY_PENDING_CLEAN_VM`
- commit：`0bfc1adc07d8b6b01adc5881bf04e31323510566`
- workflow run：`27925270250`，Windows job 成功并通过 packaged-sidecar health check
- artifact：`godot-bridle-windows-0bfc1adc07d8b6b01adc5881bf04e31323510566`
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
- 旧 onefile 候选包人工测试出现 sidecar 控制台窗口、约 93–116 秒启动延迟和 GUI 假死，判定为
  V4 阻塞缺陷。
- 修复后 sidecar 改为 onedir Tauri resource，Windows 使用 `CREATE_NO_WINDOW`，前端等待并限制
  `sidecar.ready` 启动时间；本地主机复测无 sidecar 窗口、5 秒内完成 health、GUI 正常显示，
  正常关闭后无残留 sidecar。
- Windows 对 Tauri/WebView 主进程的 `Responding` 属性可能误报；人工验收应以实际交互、RPC
  状态和窗口关闭行为为准。以上结果仍需在新候选包和干净 VM 复测。
