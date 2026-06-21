# v0.1-alpha 验证证据

本目录只保存脱敏的验证记录。不得提交 API key、完整 Provider 响应、用户目录、访问令牌或
包含 Secret 的日志。每项记录必须包含 commit SHA、执行时间、执行环境、产物 SHA-256、步骤、
实际结果、失败项和验证人。

| 阶段 | 记录 | 完成条件 |
|---|---|---|
| V1 | `v1-ci.md` | 默认分支全绿、分支保护回读、environment/Secret 名称回读 |
| V2 | `v2-linux.md` | 独立 Linux 实机完成 AppImage/deb 和桌面 E2E |
| V3 | `v3-providers.md` | 人工批准的真实 Provider smoke 与脱敏检查通过 |
| V4 | `v4-windows.md` | 干净 Windows 11 Sandbox/VM 完成 NSIS 全矩阵 |
| V5 | `v5-release.md` | 九项 Exit Criteria 签字且无未关闭阻塞项 |

未执行的项目写 `PENDING`，不得预先勾选。
