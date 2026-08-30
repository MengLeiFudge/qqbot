# NapCat 账号项目

本目录由 qqbot 根仓库管理，负责四个 QQ 账号的 NapCat/OneBot 接入，不属于 AstrBot 或 MaiBot。

## 可提交内容

- `accounts.json`：账号名称、QQ、固定 OneBot 端口、连接方向和当前框架归属。
- `scripts/configure-account.ps1`：把账号清单落实到本机 OneBot 配置。
- `scripts/ensure-account.ps1`：按账号确保配置、内置插件、进程和端口 ready。
- `scripts/start-account.ps1`：兼容 NapCat OneKey 启动器的底层单账号入口。
- `scripts/ensure-builtin-plugin.ps1`：校验或恢复官方内置插件。
- `scripts/update.ps1`：显式更新 NapCat 最新稳定 Release，并迁移账号配置。

## 本机运行态

`onekey/` 和 `data/` 被根 `.gitignore` 排除：

- `onekey/` 保存 NapCat 程序包、QQ 登录态、缓存和 `onebot11_<QQ>.json` 实际配置。
- `data/` 保存账号日志、快速登录标记、下载、归档和更新状态。

这些目录可能包含 token、登录态和日志，不得强制加入 Git。更新器替换 OneKey 包后会迁移已有账号配置，并重新按 `accounts.json` 校正连接方向和端口。

## 固定端口

- 云栖 `1443944862`：reverse client -> `ws://127.0.0.1:6200/ws`
- 夜凛 `2629227874`：forward server `127.0.0.1:6201`
- 星遥 `3056830689`：forward server `127.0.0.1:6202`
- 月澄 `3109326090`：forward server `127.0.0.1:6203`

根 `all/yunqi/yelin` 入口只自动管理云栖和夜凛。单独维护星遥或月澄时可在 Windows PowerShell 中运行：

```powershell
.\scripts\ensure-account.ps1 -Target xingyao
.\scripts\ensure-account.ps1 -Target yuecheng
```

首次登录可能需要二维码。快速登录成功标记位于 `data/quick-login/<QQ>.ready`；标记和实际登录态均只属于本机。
