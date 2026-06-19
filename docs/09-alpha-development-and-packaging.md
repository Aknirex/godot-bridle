# v0.1-alpha 开发与打包

## 前置条件

- Python 3.11+ 与 `uv`
- Node.js 20+ 与 npm
- Rust stable，以及 Tauri v2 对应的系统依赖
- 可选：Godot 4 可执行文件、`DEEPSEEK_API_KEY`、`MESHY_API_KEY`

## Python core

```bash
uv sync --extra dev
uv run pytest -q
uv run bridle health
```

真实 API smoke test 默认跳过。配置 BYOK 后显式运行：

```bash
uv run pytest -m external_api -q
```

## 桌面开发

```bash
cd desktop
npm install
npm run tauri dev
```

Tauri 主进程从仓库根目录启动 `uv run bridle sidecar`。stdout 只承载 JSON Lines
协议；诊断信息必须写 stderr 或日志文件。开发环境必须确保 `uv` 位于 `PATH`。

## Mock 验收路径

1. 在 Project 页输入含 `project.godot` 的目录并打开。
2. 在 Providers 页确认 `meshy_mock` 状态为 `ok`。
3. 在 Generate 页保留 `meshy_mock`，输入角色描述并提交。
4. Jobs 页应持续显示 12 个阶段，最终出现 `asset.generated` 和 `job.succeeded`。
5. 项目内应生成 `res://bridle/generated/<asset_id>/bridle_asset.json`。

## 打包

```bash
cd desktop
npm run tauri build
```

当前 alpha 桌面包依赖目标机器上的 Python 与 `uv`。发布自包含安装包前，需要将 Python
core 构建为平台 sidecar 二进制，并在 `tauri.conf.json` 的 `bundle.externalBin` 中声明。
Windows 首发包还需在干净 Windows VM 上验证 WebView2、路径编码、Godot executable 查找和
sidecar 终止行为。
