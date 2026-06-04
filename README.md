# QQBot Workspace

这是本机机器人 monorepo 工作区，按运行组件拆分：

- `nonebot2/`：天使棉花糖，原 qqbot / NoneBot2 应用。
- `astrbot/`：AstrBot 上游源码快照和本机配置示例；实际 bot2 Core 由 `uv tool` 管理。
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

可提交配置模板只放在：

- `nonebot2/config/env.example`：敏感环境变量和本机账号示例。
- `nonebot2/config/qqbot.toml.example`：非敏感运行配置示例。
- `astrbot/config/`：AstrBot 插件和本机配置示例。

不要再使用 `nonebot2/.env`、`nonebot2/.env.example` 或 `nonebot2/config/qqbot.toml` 作为运行配置入口；根级启动脚本会固定读取 `data/nonebot2/config/`。

AstrBot Core 不再从 `astrbot/` 源码快照启动；`scripts/start-astrbot.ps1` 会调用 `uv tool` 安装的 `astrbot` 命令，并通过 `ASTRBOT_ROOT=D:\project\qqbot\data\astrbot` 读取真实数据。

## 启动

日常入口：

```powershell
Set-Location D:\project\qqbot
.\scripts\start-nonebot2.bat
.\scripts\start-astrbot.bat
.\scripts\start-all.bat
```

三个入口分别负责启动/重启 bot1、bot2、bot1+bot2。每个入口会拉起对应 Bot 和 NapCat 子窗口，子窗口确认就绪后退出；全部子窗口完成后入口窗口退出。

管理端重启入口不会打开 Windows Terminal 标签页；它会后台启动 NoneBot2，等待 `8080` 和 OneBot 连接，并复用已经登录的 NapCat。

默认账号链路：

- `1443944862`：NapCat 反连 NoneBot2，`ws://127.0.0.1:8080/onebot/v11/ws`。
- `2629227874`：NapCat 反连 AstrBot，`ws://127.0.0.1:6199/ws`。

NapCat 仍使用 `napcat/` 下的一键包；后续再把账号配置和登录态收拢到 `data/napcat/`。

## 更新

AstrBot Core 使用手动更新入口：

```powershell
Set-Location D:\project\qqbot
.\scripts\update-astrbot.bat
```

该脚本默认使用当前 Windows 已安装的 Python 3.14，执行 `uv tool upgrade astrbot --python 3.14`；如果本机还没有安装 AstrBot tool，则改为 `uv tool install astrbot --python 3.14`。如果 Windows PATH 找不到 `uv`，脚本会先用 `py -3.14 -m pip install --user -U uv` 安装用户级 uv。更新日志写入 `data/astrbot/logs/updates/`。

更新后使用 `scripts\start-astrbot.bat` 启动 bot2。修改 `astrbot/` 里的源码快照不会影响实际运行的 bot2，除非重新切换回源码模式。
