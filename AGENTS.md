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
- `astrbot/`：AstrBot 当前工作树快照；不保留 AstrBot 上游 Git 历史。
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

## 验证

- 结构变更后至少检查：
  - `git status --short`
  - 根目录是否只有一个 `.git`
  - `data/` 是否未进入 Git
- NoneBot2 相关代码验证优先在 `nonebot2/` 内运行项目测试。
- AstrBot 相关代码验证优先在 `astrbot/` 内运行 ruff 和定向 pytest。
