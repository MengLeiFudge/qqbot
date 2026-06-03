# QQBot Workspace

这是本机机器人 monorepo 工作区，按运行组件拆分：

- `nonebot2/`：天使棉花糖，原 qqbot / NoneBot2 应用。
- `astrbot/`：恶魔棉花糖，AstrBot 应用当前工作树快照。
- `napcat/`：共用 NapCat / QQ 登录端程序包。
- `data/`：统一运行态数据目录，默认不进 Git。
- `scripts/`：根级 Windows 启动脚本。

## 数据目录

`data/` 存放真实配置、数据库、日志、QQ 登录态、AI 会话和插件数据。

- `data/nonebot2/config/`：NoneBot2 的 `.env`、`qqbot.toml`。
- `data/nonebot2/run/`：NoneBot2 运行态。
- `data/nonebot2/logs/`：NoneBot2 启动和运行日志。
- `data/astrbot/data/`：AstrBot 的 `cmd_config.json`、`data_v4.db`、插件和插件数据。
- `data/napcat/`：预留给 NapCat 账号配置、登录态和日志。

## 启动

PowerShell:

```powershell
Set-Location D:\project\qqbot
.\scripts\start-nonebot2.ps1
.\scripts\start-astrbot.ps1
.\scripts\start-napcat.ps1
```

统一启动：

```powershell
.\scripts\start-all.ps1
```

默认会通过 Windows Terminal 打开一个窗口，并把 NoneBot2、AstrBot 和两个 NapCat 账号放在不同标签页。

默认账号链路：

- `1443944862`：NapCat 反连 NoneBot2，`ws://127.0.0.1:8080/onebot/v11/ws`。
- `2629227874`：NapCat 反连 AstrBot，`ws://127.0.0.1:6199/ws`。

NapCat 仍使用 `napcat/` 下的一键包；后续再把账号配置和登录态收拢到 `data/napcat/`。
