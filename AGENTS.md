# AGENTS.md - QQBot Monorepo 工作流程

本仓库是机器人运行工作区，包含多个应用和共用协议端。

## 基本原则

- 默认使用简体中文沟通。
- 修改前先确认目标子目录：`nonebot2/`、`astrbot/`、`napcat/`、`scripts/`、`data/`。
- 不把真实 token、QQ 登录态、数据库、运行日志或本机配置提交进 Git。
- 完成可验证改动后需要提交，除非用户明确要求暂不提交。
- 严禁 push，除非用户明确批准。

## 目录边界

- `nonebot2/`：原 qqbot / NoneBot2 应用；子目录内的 `AGENTS.md` 是该应用的细化规则。
- `astrbot/`：AstrBot 上游源码快照和本机配置示例；不保留 AstrBot 上游 Git 历史，也不作为 bot2 Core 的日常启动来源。
- `napcat/`：共用 NapCat 程序包；账号数据和登录态应放在 `data/napcat/`。
- `data/`：统一运行态根目录，默认忽略，不进 Git。
- `scripts/`：monorepo 根级启动脚本，负责设置各应用运行态路径。

## 数据路径

- NoneBot2 启动时应设置：
  - `QQBOT_CONFIG_FILE=D:\project\qqbot\data\nonebot2\config\qqbot.toml`
  - `QQBOT_DATA_ROOT=D:\project\qqbot\data\nonebot2\run`
- AstrBot 启动时应设置：
  - `ASTRBOT_ROOT=D:\project\qqbot\data\astrbot`
  - AstrBot 实际数据目录为 `D:\project\qqbot\data\astrbot\data`
  - Core 由 `uv tool` 管理，启动脚本调用 `astrbot run -p 6185` 或 `uv tool run --from astrbot --python 3.14 astrbot run -p 6185`

## 验证

- 结构变更后至少检查：
  - `git status --short`
  - 根目录是否只有一个 `.git`
  - `data/` 是否未进入 Git
- NoneBot2 相关代码验证优先在 `nonebot2/` 内运行项目测试。
- AstrBot 相关代码验证优先在 `astrbot/` 内运行 ruff 和定向 pytest。
- AstrBot Core 运行/更新脚本变更优先做 PowerShell 语法检查；不要把源码快照测试结果当作 uv tool 运行态验证。

## 启动与重启

- 日常启动入口是 `D:\project\qqbot\scripts\start-nonebot2.bat`、`scripts\start-astrbot.bat`、`scripts\start-all.bat`，分别启动/重启 bot1、bot2、bot1+bot2。
- 普通启动入口会拉起对应 Bot 和 NapCat 子窗口；子窗口确认端口和反连就绪后退出，全部子窗口完成后入口窗口退出。
- 管理端重启入口使用 `scripts/start-nonebot2.bat -SkipInstall -RestartBot` 后台编排，只重启 NoneBot2，等待 `8080` 和 OneBot 连接，不额外打开 NapCat 窗口。
- `-RestartBot` 模式日志写入 `data\nonebot2\logs\start_all\<timestamp>\`。

## 更新

- AstrBot Core 手动更新入口是 `D:\project\qqbot\scripts\update-astrbot.bat`。
- `update-astrbot.bat` 默认调用 `uv tool upgrade astrbot --python 3.14`；如果未安装则调用 `uv tool install astrbot --python 3.14`。
- Windows PATH 找不到 `uv` 时，更新脚本可以用 `py -3.14 -m pip install --user -U uv` 自举用户级 uv。
- 更新日志写入 `data\astrbot\logs\updates\`，真实数据仍在 `data\astrbot\data\`。
- 切换到 uv tool 后，修改 `astrbot\` 源码快照不会影响实际运行的 bot2；不要用 `astrbot\` 的源码 diff 判断线上 AstrBot Core 是否已更新。
