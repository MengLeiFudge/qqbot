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
- AstrBot 行为调整硬限制：配置优先，插件其次，绝不直接修改 AstrBot Core 源码。能通过 `data/astrbot/data/` 运行态配置、AstrBot 参数或插件实现的行为，不允许改 `astrbot/` 源码快照或 uv tool 安装目录源码；只有先确认配置和插件都无法实现，并获得用户明确批准后，才允许讨论 Core 补丁。
- `astrbot-local-plugins/`：本仓库维护的 AstrBot 本地插件源码；`scripts/start-astrbot.ps1` 启动前同步到 `data/astrbot/data/plugins/`。新增或迁移 bot2 功能时优先放这里，避免直接修改 `astrbot/` Core 源码或把 `data/` 运行态纳入 Git。
- 迁移 NoneBot2 功能到 AstrBot 本地插件时，必须明确 bot1/bot2 双开和 AstrBot-only 两种模式下的功能归属。默认使用 `dual` 模式：bot2 只响应明确唤醒或私聊命令，复读、入群欢迎、戳一戳等自动事件仍由 bot1 负责；只有 AstrBot-only 场景才允许使用 `full` 模式接管已迁移自动事件。
- bot1/bot2 联动优先用 AstrBot 本地插件桥接，不改 Core。桥接插件只能只读 `data\nonebot2\run\ai\group_context\` 这类公开群上下文，默认不按具体群号限制；星环群 `1035445959` 只能作为领域提示特例，不能作为桥接范围条件。不得读取私聊、token、QQ 登录态、数据库密钥或运行日志作为 LLM prompt 证据。
- AstrBot 源码知识兜底优先用 `astrbot_plugin_source_knowledge` 这类本地插件实现，不改 Core、不依赖 Embedding。可信依据必须优先来自源码、反编译源码、源码邻近 README/设计文档和配置数据，尤其是戴森球计划本体相关源码和相关 mod 源码；群聊、群文件、攻略和 release notes 只能作为候选或补充。源码检索插件只读明确配置的源码根，必须跳过 `.git`、`.codex`、`bin`、`obj`、`.vs`、`.idea`、`packages`、`node_modules`、`logs`、缓存和密钥类文件；不得读取私聊、token、QQ 登录态、数据库密钥、运行日志或本仓库运行态 `data`。
- bot1/bot2 共用本地表情包索引 `data\memes\mlj_pack\index.json`；`auto_send_enabled=false` 的敏感支付、涩涩慎用、待复核类别不得自动发送。AstrBot 侧通过 `scripts\sync-meme-pack.py` 同步到 `data\astrbot\data\plugin_data\meme_manager\` 和运行态配置，不改 Core、不删除旧图库目录。
- bot1/bot2 双开时，普通主动接话不得由另一个 bot 的普通输出继续触发；明确 @ 当前 bot 或私聊仍按直接请求处理。两个 bot 的普通回复、主动回复和拒答都不要反问，不要用“如果你愿意”“要的话”“你把具体名字发我”“我可以再帮你”等追问式收尾；缺关键信息时陈述缺口，不催用户补充。
- bot1/bot2 的所有群聊和私聊 LLM 回复都不做危机处理；自述、倒霉、考试迟到、没吃饭、没睡觉等默认按玩笑、夸张、钓机器人或时间梗分析。分析不出发言原因时不回答，不编原因，不输出危机干预、急救、报警、健康建议或严肃安慰；凭据泄露等本地硬安全提醒仍按既有规则执行。
- `napcat/`：共用 NapCat 程序包；更新下载和旧包备份应放在 `data/napcat/`，当前账号 OneBot 配置随一键包放置并由更新脚本迁移。
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
- NoneBot2 测试套件已移除；相关代码验证优先使用 `python -m py_compile`、启动探针、管理端状态检查或更窄的运行时复核。
- AstrBot 测试套件已移除；相关代码验证优先在 `astrbot/` 内运行 ruff、`python -m py_compile` 和实际 uv tool 启动探针。
- AstrBot Core 运行/更新脚本变更优先做 PowerShell 语法检查；不要把源码快照测试结果当作 uv tool 运行态验证。

## 启动与重启

- 日常启动入口是 `D:\project\qqbot\scripts\start-nonebot2.bat`、`scripts\start-astrbot.bat`、`scripts\start-all.bat`，分别启动/重启 bot1、bot2、bot1+bot2。
- 修改会影响正在运行机器人的代码、配置、提示词、运行包或启动脚本后，必须重启对应机器人并做启动验证；不能只停在“已修改/已提交”。若当前环境无法重启，最终回复必须明确写出未重启、原因和应执行的入口。
- 只影响 `nonebot2/` 或 `data\nonebot2\config` 的改动，重启 bot1：`scripts\start-nonebot2.bat -SkipInstall -RestartBot`。
- 只影响 AstrBot Core、`data\astrbot\data\cmd_config.json`、AstrBot persona 或 uv tool 运行包的改动，重启 bot2：`scripts\start-astrbot.bat`。
- 只运行 AstrBot 并希望接管已迁移自动事件时，使用 `scripts\start-astrbot.bat -FeatureMode full`；双开 bot1/bot2 时不要使用 `full`。
- 同时影响 bot1 和 bot2，使用 `scripts\start-all.bat`；需要 NapCat 重新反连时也使用普通启动入口，不要只重启 Python 进程。
- 普通启动入口会拉起对应 Bot 和 NapCat 子窗口；子窗口确认端口和反连就绪后退出，全部子窗口完成后入口窗口退出。
- NapCat 启动脚本必须同时兼容新版 `napcat\onekey\napcat\launcher-user.bat` 和旧版 `NapCat.*.Shell` / `bootmain` 结构；新版 quick login 使用 `NAPCAT_QUICK_ACCOUNT` 环境变量。
- 管理端重启入口使用 `scripts/start-nonebot2.bat -SkipInstall -RestartBot` 后台编排，只重启 NoneBot2，等待 `8080` 和 OneBot 连接，不额外打开 NapCat 窗口。
- `-RestartBot` 模式日志写入 `data\nonebot2\logs\start_all\<timestamp>\`。

## 更新

- AstrBot Core 手动更新入口是 `D:\project\qqbot\scripts\update-astrbot.bat`。
- 总更新入口是 `D:\project\qqbot\scripts\update-all.bat`，按顺序调用 NapCat、NoneBot2/OneBot adapter、AstrBot 更新入口。
- NapCat 手动更新入口是 `D:\project\qqbot\scripts\update-napcat.bat`；正式更新会先停止本工作区关联的 NapCat/QQ 进程，再把旧 `napcat\onekey` 备份到 `data\napcat\archives\`，替换后迁移账号 OneBot 配置。
- NoneBot2/OneBot adapter 手动更新入口是 `D:\project\qqbot\scripts\update-nonebot2.bat`；只按 `nonebot2\pyproject.toml` 版本约束升级依赖，不自动放宽主版本上限。
- OneBot v11 本身是协议；本仓库实际更新对象是 NapCat 协议端和 `nonebot-adapter-onebot`。
- `update-astrbot.bat` 默认调用 `uv tool upgrade astrbot --python 3.14`；如果未安装则调用 `uv tool install astrbot --python 3.14`。
- Windows PATH 找不到 `uv` 时，更新脚本可以用 `py -3.14 -m pip install --user -U uv` 自举用户级 uv。
- 更新日志写入 `data\astrbot\logs\updates\`，真实数据仍在 `data\astrbot\data\`。
- 切换到 uv tool 后，修改 `astrbot\` 源码快照不会影响实际运行的 bot2；不要用 `astrbot\` 的源码 diff 判断线上 AstrBot Core 是否已更新。
