# QQBot Workspace

这是本机机器人 monorepo 工作区，按运行组件拆分：

- `nonebot2/`：原 qqbot / NoneBot2 应用源码，当前作为功能存档和纯 Python service 复用来源。
- `astrbot/`：AstrBot 上游源码快照和本机配置示例；实际 AstrBot Core 由 `uv tool` 管理。
- `astrbot-local-plugins/`：本仓库维护的 AstrBot 本地插件源码，启动 AstrBot 前同步到运行态插件目录。
- `napcat/`：共用 NapCat / QQ 登录端程序包。
- `data/`：统一运行态数据目录，默认不进 Git。
- `scripts/`：根级 Windows 启动脚本。

## 数据目录

`data/` 存放真实配置、数据库、日志、QQ 登录态、AI 会话、插件数据和更新备份。

- `data/nonebot2/config/`：NoneBot2 的 `.env`、`qqbot.toml`。
- `data/nonebot2/run/`：迁移期历史存档和可复用功能状态。
- `data/nonebot2/logs/`：旧 NoneBot2 启动和运行日志。
- `data/astrbot/data/`：AstrBot 的 `cmd_config.json`、`data_v4.db`、插件和插件数据。
- `data/memes/mlj_pack/`：AstrBot 使用的本地表情包运行态副本和 `index.json`；敏感、涩涩、待复核类别默认不自动发送。
- `data/napcat/`：NapCat 更新下载、旧包备份、账号配置、登录态和日志。

可提交配置模板只放在：

- `nonebot2/config/env.example`：敏感环境变量和本机账号示例。
- `nonebot2/config/qqbot.toml.example`：非敏感运行配置示例。
- `astrbot/config/`：AstrBot 插件、本机配置和人格示例；可用 `python3 scripts/export-astrbot-config-examples.py` 从当前运行态重新导出，脚本会剔除 LLM provider/model 路由并脱敏 key/token/secret。

不要再使用 `nonebot2/.env`、`nonebot2/.env.example` 或 `nonebot2/config/qqbot.toml` 作为运行配置入口；根级启动脚本会固定读取 `data/nonebot2/config/`。

AstrBot Core 不再从 `astrbot/` 源码快照启动；`scripts/start-astrbot.ps1` 会优先直调 `uv tool` 安装出的 `astrbot.exe`，再回退到 PATH 中的 `astrbot` / `uv tool run`，并通过 `ASTRBOT_ROOT=D:\project\qqbot\data\astrbot` 读取真实数据。

`astrbot-local-plugins/` 下的本地插件会在 `scripts/start-astrbot.ps1` 启动前复制到 `data\astrbot\data\plugins\`。当前 `astrbot_plugin_qqbot_features` 负责承接从 NoneBot2 迁移到 AstrBot 的本地功能入口：功能清单、图片菜单、Factorio 下载链接、复读、入群欢迎、戳一戳文本响应、按配置自动同意好友申请和邀请入群、群文件清理通知、主人限定群聊记录导出、shapez 短代码渲染、Arc PTT 推荐、活动梯子查询、字母猜歌、曲绘猜歌、作者限定安装包下载、养鲲、落樱之都基础玩法、Lolicon 基础取图和 Lolicon 群配置、RightCodes 生图和生图积分；NoneBot2 AI runtime 使用 AstrBot 原生链路替代。

`astrbot_plugin_local_artifact_api` 负责 AstrBot 的本地构建产物发布兼容入口。AstrBot `full` 模式下会在 `127.0.0.1:8080` 提供 `POST /admin/api/artifacts/publish-local`，保持原 NoneBot2 localhost-only 请求体、Git 上下文校验、SHA 跳过策略和 OneBot 群文件上传行为，供 `AfterBuildEvent.exe 1` 这类本机白名单构建流程继续发布 zip 产物。
`scripts\start-all.ps1 -Target astrbot -FeatureMode full` 会清理旧的 `8080` 占用，并在启动验证中等待 `6185`、`6200/6201` 和 `8080` 都就绪；如果 artifact API 绑定失败，启动入口会失败而不是只报告 AstrBot WebUI ready。

RightCodes 生图命令已归入 `astrbot_plugin_qqbot_features`。默认复用 `data\nonebot2\run\ai\draw_points.json` 迁移期积分存档；双平台 `both/full` 下只有固定命令 owner 账号累计普通群消息积分，避免天使和恶魔同群时同一消息重复记分。RightCodes API Key 直接填写在 AstrBot 插件配置 `astrbot_plugin_qqbot_features.api_key`，不再读取 `QQBOT_AI_KEY_RIGHTCODES` 或 NoneBot2 `.env`。生图成功、失败或超时失败都会引用原始请求；默认 240 秒总超时，超时失败会退回本次扣除的积分或免费次数。

RightCodes 生图接口问答也归入 `astrbot_plugin_qqbot_features` 的静态知识 catalog。用户问 RightCodes 画图接口、请求体、`size`、`1024x1024`、`/v1/images/generations` 或 `/v1/chat/completions` 时，插件会在 LLM 请求前注入官方文档摘要：`/v1/images/generations` 支持 `size` 字段，`/v1/chat/completions` 适合流式防超时。

`astrbot_plugin_qqbot_features` 默认按 `full` 模式运行，由 AstrBot 接管已迁移自动事件。旧 `dual` 配置仅作为兼容值保留，运行时也按 `full` 处理。日常使用 `scripts\start-astrbot.bat` 或 `scripts\start-all.bat` 启动同一 AstrBot 管理端内的天使+恶魔双平台。

AstrBot 启动入口支持显式选择 bot 身份：默认 `-AstrBotProfile demon` 使用恶魔棉花糖账号 `2629227874`；`-AstrBotProfile angel -FeatureMode full` 使用天使账号 `1443944862`；`-AstrBotProfile both -FeatureMode full` 在同一个 AstrBot 管理端里同步两个 `aiocqhttp` 平台，恶魔默认反连 `ws://127.0.0.1:6200/ws`，天使默认反连 `ws://127.0.0.1:6201/ws`。`scripts\start-astrbot.bat` 和 `scripts\start-all.bat` 默认就是 `both/full`。本地插件会按每条消息的 `self_id` 区分天使或恶魔身份。

`scripts\start-all.ps1` 会先让 bot 子流程完成旧端口清理，再提前启动对应 NapCat 子流程；NapCat 子流程等待目标 OneBot 端口监听后立即连接，不再等 AstrBot 全部 ready 后才开始准备。AstrBot 反向 WebSocket 端口如果出现 `WinError 10013`、`PermissionError` 等平台绑定错误，启动器会从日志中快速识别并失败，不再等满长超时。

AstrBot 双平台下，普通闲聊和主动接话允许两个棉花糖共同参与；固定命令只由一个账号执行。没有明确 @ 或私聊时，固定命令默认由恶魔账号 `2629227874` 处理，可用 `QQBOT_ASTRBOT_COMMAND_OWNER` 覆盖；明确 @ 天使/恶魔或私聊时，由当前被叫到的 bot 处理。`菜单`、`帮助`、`指令` 会发送统一图片菜单，总览按 `群务管理`、`棉花糖互动`、`养鲲`、`落樱之都`、`Arcaea`、`Factorio`、`异形工厂` 分组；`菜单模块名` 会发送模块详情图。

`astrbot_plugin_qqbot_context_bridge` 负责迁移期公开群上下文复用：AstrBot 发起群聊 LLM 请求时，会按当前群号读取历史公开群上下文 `data\nonebot2\run\ai\group_context\<群号>.json` 并注入本轮请求。默认不限制群号，只要有对应公开群上下文文件就桥接；`enabled_groups` 只作为可选 allowlist。星环群 `1035445959` 额外带 OrbitalRing 领域提示，但不作为桥接范围条件。插件不读取私聊、日志、token 或其他敏感运行态。

`astrbot_plugin_twin_interaction` 负责天使/恶魔两个棉花糖的双子互动增强：当用户明确围绕天使、恶魔、姐姐/妹妹、双子关系或另一个 bot 的公开输出发问时，插件会给本轮 LLM 请求注入当前 bot、另一个 bot 的账号事实、互动边界和少量同群公开上下文。它不注入固定人设或语气文本，只让当前 bot 用自己的 WebUI 人格回应，不替另一个 bot 发言、认错、解释或承诺修改；另一个 bot 发出的普通消息不会触发当前 bot 自动接话。

`astrbot_plugin_source_knowledge` 负责 bot2 的源码知识兜底：在没有 Embedding 模型、不能使用 AstrBot 原生知识库时，它会按当前群号和问题文本只读检索本机源码树，并把少量相关源码片段临时注入本轮 LLM 请求。默认源码根覆盖 DSPCore、万物分馏、星环、创世之书、shapez 和 Factorio 模组源码；可信依据优先是源码、反编译源码、源码邻近 README/设计文档和配置数据。插件跳过 `.git`、`.codex`、`bin`、`obj`、`.vs`、`.idea`、`packages`、`node_modules`、`logs`、缓存和密钥类文件，不读取私聊、运行日志、token、QQ 登录态、运行态 `data` 或数据库密钥。

`astrbot_plugin_topic_concentration` 负责 AstrBot 的普通群聊主动接话门控：保留 AstrBot Core 的主动回复开关、群聊、非 @、白名单和 method 硬门槛，再用短窗口话题判断、弱窗口过滤、同群 in-flight、组级冷却、同话题冷却和双子账号消息过滤决定是否放行。它不主动发送最终回复，只控制 Core active reply 是否继续执行。普通主动接话的 provider 选择、模型切换和回退链只使用 AstrBot 当前会话配置；插件不提供独立 provider 顺序或判定专用模型配置，判定失败时静默跳过本次普通主动接话。明确出现“棉花糖”“棉花糖在吗”“呼叫棉花糖”等命名呼叫时，插件本地直接放行当前选中的普通 LLM worker；同一用户短时间内紧接“在吗”等探活短句也继承这次呼叫，不依赖主动接话判定 provider。明确 @ 和私聊不会被主动接话 in-flight 拦截。

`astrbot_plugin_qqbot_features` 负责已迁移的群务、菜单、生图、游戏和固定命令。好友申请和邀请入群默认按配置自动同意；机器人自身入群成功后会优先私聊通知邀请者，文案包含群名和群号，不在群聊里发送“主人”自报。双平台 `both/full` 下，天使和恶魔会各自按身份发送新成员入群欢迎，并各自独立随机选择旧四选一群地位后缀；双子自身入群不会触发欢迎。

`astrbot_plugin_reply_style_guard` 负责发送前清洗 Markdown、末尾问句和追问式邀请，记录 LLM 耗时，并控制过多分段。非“主人私聊”时，插件会在 LLM 请求前剔除本机命令、Python、文件读写、grep、浏览器、上传下载等运行态工具；发送前会移除引导用户去 WebUI 添加管理员、开启 shell 或文件权限的内容。插件不再向 LLM 请求注入固定人设、固定水群风格或输出风格提示词；天使/恶魔身份、说话风格和群聊氛围只由 AstrBot WebUI 人格配置提供。插件会在本地日志记录 LLM 请求开始、模型返回和发送前装饰耗时，不记录完整 prompt 或回复正文；按当前 AstrBot 分段正则预估会拆成 4 条以上的 LLM 回复不再分段。长作文或慢请求不按固定秒数丢弃，是否失败以 provider timeout/error/fallback 日志为准。

普通聊天文本不会因为 `在吗`、`111`、`真的吗`、`回复慢`、`低信息` 或测试探活这类启发式在本地插件里直接生成固定回复；没有命中明确命令、游戏会话答案、协议事件处理或本地硬安全提醒时，统一交给 LLM 链路。

本地表情包由 `data\memes\mlj_pack\index.json` 描述每张图的分类、用途和禁用场景。`scripts\sync-meme-pack.py` 会把可自动发送类别同步到 AstrBot `meme_manager` 运行态目录，并把轻松日常、玩梗、吐槽、撒娇、短情绪回复调成优先使用表情；短情绪闲聊允许只发一张表情不带文字，技术、报错、安全、群管理和长解释场景不自动附图。

## 启动

日常入口：

```powershell
Set-Location D:\project\qqbot
.\scripts\start-nonebot2.bat
.\scripts\start-astrbot.bat
.\scripts\start-all.bat
```

日常入口是 `start-astrbot.bat` 或 `start-all.bat`，两者默认启动 AstrBot 的天使+恶魔双平台。`start-nonebot2.bat` 只作为旧 NoneBot2 存档调试入口保留。每个入口会拉起对应 Bot 和 NapCat 子窗口，子窗口确认就绪后退出；全部子窗口完成后入口窗口退出。

旧 NoneBot2 管理端重启入口不会打开 Windows Terminal 标签页；它只用于调试存档代码，不是日常机器人运行入口。

默认账号链路：

- `1443944862`：AstrBot 天使平台，默认反连 `ws://127.0.0.1:6201/ws`。
- `2629227874`：NapCat 反连 AstrBot 恶魔平台，默认 `ws://127.0.0.1:6200/ws`。

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
