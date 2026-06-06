# QQBot Workspace

这是本机机器人 monorepo 工作区，按运行组件拆分：

- `nonebot2/`：天使棉花糖，原 qqbot / NoneBot2 应用。
- `astrbot/`：AstrBot 上游源码快照和本机配置示例；实际 bot2 Core 由 `uv tool` 管理。
- `astrbot-local-plugins/`：本仓库维护的 AstrBot 本地插件源码，启动 bot2 前同步到运行态插件目录。
- `napcat/`：共用 NapCat / QQ 登录端程序包。
- `data/`：统一运行态数据目录，默认不进 Git。
- `scripts/`：根级 Windows 启动脚本。

## 数据目录

`data/` 存放真实配置、数据库、日志、QQ 登录态、AI 会话、插件数据和更新备份。

- `data/nonebot2/config/`：NoneBot2 的 `.env`、`qqbot.toml`。
- `data/nonebot2/run/`：NoneBot2 运行态。
- `data/nonebot2/logs/`：NoneBot2 启动和运行日志。
- `data/astrbot/data/`：AstrBot 的 `cmd_config.json`、`data_v4.db`、插件和插件数据。
- `data/napcat/`：NapCat 更新下载、旧包备份、账号配置、登录态和日志。

可提交配置模板只放在：

- `nonebot2/config/env.example`：敏感环境变量和本机账号示例。
- `nonebot2/config/qqbot.toml.example`：非敏感运行配置示例。
- `astrbot/config/`：AstrBot 插件和本机配置示例。

不要再使用 `nonebot2/.env`、`nonebot2/.env.example` 或 `nonebot2/config/qqbot.toml` 作为运行配置入口；根级启动脚本会固定读取 `data/nonebot2/config/`。

AstrBot Core 不再从 `astrbot/` 源码快照启动；`scripts/start-astrbot.ps1` 会调用 `uv tool` 安装的 `astrbot` 命令，并通过 `ASTRBOT_ROOT=D:\project\qqbot\data\astrbot` 读取真实数据。

`astrbot-local-plugins/` 下的本地插件会在 `scripts/start-astrbot.ps1` 启动前复制到 `data\astrbot\data\plugins\`。当前 `astrbot_plugin_qqbot_features` 负责承接从 NoneBot2 迁移到 AstrBot 的本地功能入口：功能清单、菜单、Factorio 下载链接、复读、入群欢迎、戳一戳响应，以及社交请求日志；群文件清理、Lolicon、养鲲、落樱、Arc、shapez 和 NoneBot2 AI runtime 属于二期适配或使用 AstrBot 原生链路。

`astrbot_plugin_qqbot_features` 默认使用 `dual` 模式：bot1 和 bot2 同时在线时，AstrBot 只响应明确唤醒或私聊命令，复读、入群欢迎、戳一戳等自动事件仍由 NoneBot2 负责，避免同一事件双机器人重复回应。以后切换到 AstrBot-only 时，先停用 bot1，再使用 `scripts\start-astrbot.bat -FeatureMode full` 启动 bot2，或在 AstrBot 插件配置中把 `feature_mode` 改为 `full` 后重启 bot2；环境变量 `QQBOT_ASTRBOT_FEATURE_MODE` 会覆盖插件配置。启动脚本会阻止 `full` 模式和 NoneBot2 双开。

`astrbot_plugin_qqbot_context_bridge` 负责 bot1/bot2 的轻量联动：bot2 发起群聊 LLM 请求时，会按当前群号读取 bot1 的公开群上下文 `data\nonebot2\run\ai\group_context\<群号>.json` 并注入本轮请求。默认不限制群号，只要 bot1 有对应公开群上下文文件就桥接；`enabled_groups` 只作为可选 allowlist。星环群 `1035445959` 额外带 OrbitalRing 领域提示，但不作为桥接范围条件。插件不读取私聊、日志、token 或其他敏感运行态。

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

NapCat 仍使用 `napcat/` 下的一键包；更新脚本会保留并迁移账号 OneBot 配置，更新下载和旧包备份放在 `data/napcat/`。

## 更新

AstrBot Core 使用手动更新入口：

```powershell
Set-Location D:\project\qqbot
.\scripts\update-all.bat
```

分项更新入口：

```powershell
.\scripts\update-napcat.bat
.\scripts\update-nonebot2.bat
.\scripts\update-astrbot.bat
```

`update-all.bat` 会按顺序更新 NapCat、NoneBot2/OneBot adapter、AstrBot Core。

NapCat 更新会先停止本工作区关联的 NapCat/QQ 进程，再从 GitHub 最新 release 下载 Windows Shell OneKey zip，把旧 `napcat\onekey` 备份到 `data\napcat\archives\`，替换程序包后自动迁移 `napcat_*.json`、`napcat_protocol_*.json` 和 `onebot11_*.json` 账号配置。

NoneBot2 更新会按 `nonebot2\pyproject.toml` 中的版本约束升级依赖；OneBot v11 对应的 Python 适配器是 `nonebot-adapter-onebot`，随 NoneBot2 更新入口一起处理。

AstrBot 更新默认使用当前 Windows 已安装的 Python 3.14，执行 `uv tool upgrade astrbot --python 3.14`；如果本机还没有安装 AstrBot tool，则改为 `uv tool install astrbot --python 3.14`。如果 Windows PATH 找不到 `uv`，脚本会先用 `py -3.14 -m pip install --user -U uv` 安装用户级 uv。更新日志写入 `data/astrbot/logs/updates/`。

更新后使用 `scripts\start-astrbot.bat` 启动 bot2。修改 `astrbot/` 里的源码快照不会影响实际运行的 bot2，除非重新切换回源码模式。
