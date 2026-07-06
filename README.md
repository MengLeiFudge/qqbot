# QQBot Workspace

这是本机机器人 monorepo 工作区，按运行组件拆分：

- `astrbot/`：AstrBot 上游源码快照和本机配置示例；实际 AstrBot Core 由 `uv tool` 管理。
- `astrbot-local-plugins/`：本仓库维护的 AstrBot 本地插件源码，启动 AstrBot 前同步到运行态插件目录。
- `napcat/`：共用 NapCat / QQ 登录端程序包。
- `data/`：统一运行态数据目录，默认不进 Git。
- `scripts/`：只保留根级 Windows 用户入口 `start-all.bat` 和 `update-all.bat`。
- `tools/runtime-scripts/`：启动和更新入口调用的内部 PowerShell 实现。
- `tools/maintenance-scripts/`：配置导出、表情迁移这类维护脚本。

## 数据目录

`data/` 存放真实配置、数据库、日志、QQ 登录态、AI 会话、插件数据和更新备份。

- `data/astrbot/data/`：AstrBot 的 `cmd_config.json`、`data_v4.db`、插件和插件数据。
- `data/astrbot/data/plugin_data/qqbot_features_runtime/`：从旧 qqbot 迁入的轻量运行态。插件业务状态优先存放在 `db/qqbot_features.sqlite3` 和 `db/lolicon.sqlite3`；本地 artifact 发布去重状态保留在 `fe_artifacts/` 和 `local_artifacts/`；生成图片等临时文件只放 `cache/`，不再保留旧 AI 记忆、公开群上下文快照、TTS、头像和 shapez 静态旧目录。
- `data/astrbot/data/plugin_data/qqbot_features_config/`：从旧 qqbot 迁入的 `.env` 和 `qqbot.toml`，供 AstrBot 本地插件读取必要本机配置。
- `data/astrbot/data/plugin_data/meme_manager/`：`astrbot_plugin_qqbot_features` 内部表情管理模块的运行态事实源，包含 `memes/` 图片目录、`meme_index.json` 单图语义索引和兼容的 `memes_data.json` 类别描述。
- `data/memes/mlj_pack/`：旧本地表情包整理结果，仅作为迁移来源保留；不再作为日常运行事实源。
- `data/napcat/`：NapCat 更新下载、旧包备份、账号配置、登录态和日志。

可提交配置模板只放在：

- `astrbot/config/`：AstrBot 插件、本机配置和人格示例；可用 `python3 tools/maintenance-scripts/export-astrbot-config-examples.py` 从当前运行态重新导出，脚本会剔除 LLM provider/model 路由并脱敏 key/token/secret。

不要再使用旧 NoneBot2 配置入口；AstrBot 本地迁移插件读取 `data/astrbot/data/plugin_data/qqbot_features_config/`。

AstrBot Core 不再从 `astrbot/` 源码快照启动；`tools/runtime-scripts/start-astrbot.ps1` 会优先直调 `uv tool` 安装出的 `astrbot.exe`，再回退到 PATH 中的 `astrbot`，并通过 `ASTRBOT_ROOT=D:\project\qqbot\data\astrbot` 读取真实数据。日常启动不会自动使用 `uv tool run --from astrbot` 联网拉包；如果 AstrBot tool 尚未安装，先运行 `scripts\update-all.bat`。

`astrbot-local-plugins/` 下的本地插件会在 `tools/runtime-scripts/start-astrbot.ps1` 启动前复制到 `data\astrbot\data\plugins\`。当前 `astrbot_plugin_qqbot_features` 负责 AstrBot 的本地功能入口：功能清单、图片菜单、Factorio 下载链接、Sub2API 账号用量查询、复读、入群欢迎、戳一戳文本响应、本地表情包管理、按配置自动同意好友申请和邀请入群、群文件清理通知、shapez 短代码渲染、Arc PTT 推荐、活动梯子查询、字母猜歌、曲绘猜歌、作者限定安装包下载、养鲲、落樱之都基础玩法、Lolicon 基础取图和 Lolicon 群配置、RightCodes 生图和生图积分；旧 AI runtime 使用 AstrBot 原生链路替代。

`astrbot_plugin_local_artifact_api` 负责 AstrBot 的本地构建产物发布兼容入口。AstrBot `full` 模式下会在 `127.0.0.1:8080` 提供 `POST /admin/api/artifacts/publish-local`，保持原 NoneBot2 localhost-only 请求体、Git 上下文校验和 OneBot 群文件上传行为，供 `AfterBuildEvent.exe 1` 这类本机白名单构建流程继续发布 zip 产物。服务端会独立读取 zip 内容计算内容 hash，并和自己的发布缓存比对；内容未变化时不删除旧文件、不上传、不发群消息。
`tools\runtime-scripts\start-all.ps1` 日常默认等价于 `-Target astrbot -FeatureMode full -AstrBotProfile both`。默认模式是 ensure-running：如果现有 AstrBot WebUI `6185`、OneBot `6200/6201`、artifact API `8080` 和两路 NapCat 反连已经 ready，会直接复用当前运行态，避免无意义冷重启；如果端口或连接缺失，才启动缺失组件。需要强制应用插件、配置、脚本或 uv tool 运行包变更时，给 PowerShell 入口加 `-ForceRestart`，此时会清理旧端口和旧进程并重新等待 `6185`、`6200/6201` 和 `8080` 全部就绪；如果 artifact API 绑定失败，启动入口会失败而不是只报告 AstrBot WebUI ready。

RightCodes 生图命令已归入 `astrbot_plugin_qqbot_features`。生图积分事实源使用 `data\astrbot\data\plugin_data\qqbot_features_runtime\db\qqbot_features.sqlite3`；旧 `ai\draw_points.json` 首次读取时会自动导入，之后不再作为写入事实源。双平台 `both/full` 下只有固定命令 owner 账号累计普通群消息积分，避免天使和恶魔同群时同一消息重复记分。RightCodes API Key 直接填写在 AstrBot 插件配置 `astrbot_plugin_qqbot_features.api_key`，不再读取 `QQBOT_AI_KEY_RIGHTCODES` 或旧 `.env`。明确 `棉花糖生图` / `棉花生图` 命令里如果包含“仿照上面、这张图、参考、聊天记录”等上下文指代，插件会先用当前会话 AstrBot provider 把请求整理成准确生图提示词，再扣积分并调用 RightCodes；拿不到可用引用图片或上下文时不扣积分。生图成功、失败或超时失败都会引用原始请求；默认 240 秒总超时，超时失败会退回本次扣除的积分或免费次数。

RightCodes 生图接口问答也归入 `astrbot_plugin_qqbot_features` 的静态知识 catalog。用户问 RightCodes 画图接口、请求体、`size`、`1024x1024`、`/v1/images/generations` 或 `/v1/chat/completions` 时，插件会在 LLM 请求前注入官方文档摘要：`/v1/images/generations` 支持 `size` 字段，`/v1/chat/completions` 适合流式防超时。

图片理解仍使用 AstrBot Core 的 image caption 链路，不把默认回复模型临时切到 vision provider，避免回复风格漂移。当前 caption prompt 要求识图模型在有人物、动物、动漫/游戏/影视角色或作品线索时，优先返回名称、出处/作品、候选、依据和不确定性；主回复模型只读取这段 `<image_caption>`，不直接看原图。

Sub2API 账号用量查询归入 `astrbot_plugin_qqbot_features` 固定命令：群里发送 `用量` 查询配置的默认 Sub2API 账号 5h / 7d 用量窗口，默认账号名由 `sub2api_default_account_name` 控制，通常填 `Pro`。插件启动后按 `sub2api_refresh_interval_seconds` 后台定时使用 Sub2API `source=active&force=true` 刷新，默认 300 秒；群消息只返回最近一次成功缓存，不等待 Sub2API 慢请求。这个缓存按 Sub2API 账号名全局共享，不按 QQ 用户、群或 bot 身份拆分；所有 QQ 查询的都是同一个默认账号结果。若 Sub2API 返回一个匹配账号，机器人只返回这一条；若返回多个匹配账号，则按接口顺序逐个列出。`sub2api_alert_group_ids` 可填写英文逗号分隔的 QQ 群号，5h 用量首次跨过 80%、90%、95% 时自动提醒这些群；回落到阈值以下后才允许再次触发同一阈值。Sub2API 根地址和 Admin API Key 填在 AstrBot 插件运行态配置 `sub2api_base_url`、`sub2api_admin_api_key`，真实 key 不写入源码或示例配置。

`astrbot_plugin_qqbot_features` 默认按 `full` 模式运行，由 AstrBot 接管已迁移自动事件。旧 `dual` 配置仅作为兼容值保留，运行时也按 `full` 处理。日常使用 `scripts\start-all.bat` 启动同一 AstrBot 管理端内的天使+恶魔双平台。

AstrBot 启动入口支持显式选择 bot 身份：日常默认是 `both/full`，在同一个 AstrBot 管理端里同步两个 `aiocqhttp` 平台，天使默认反连 `ws://127.0.0.1:6200/ws`，恶魔默认反连 `ws://127.0.0.1:6201/ws`；只有显式 `-AstrBotProfile demon` 才使用恶魔棉花糖账号 `2629227874` 单平台，显式 `-AstrBotProfile angel -FeatureMode full` 才使用天使账号 `1443944862` 单平台。`scripts\start-all.bat` 和直接运行 `tools\runtime-scripts\start-all.ps1` 默认都是 `both/full`。本地插件会按每条消息的 `self_id` 区分天使或恶魔身份。

`tools\runtime-scripts\start-all.ps1` 默认在单个入口终端中显示启动进度，控制台摘要带固定前缀，例如 `[Launcher]`、`[AstrBot]`、`[NapCat] [Angel]`、`[NapCat] [Demon]`；完整原始日志仍写入对应 `data\astrbot\logs\start_all\<runId>\*\*.log` 文件。需要恢复旧的多子窗口观察方式时，可显式加 `-UseChildWindows`。默认 ensure-running 会先探测现有运行态；只有缺少 AstrBot 端口、NapCat 连接或显式传入 `-ForceRestart` 时，才启动子流程。强制重启模式会先让 bot 子流程完成旧端口清理，再等待 AstrBot 的 `6185`、`6200/6201` 和 `8080` 全部通过 ready 验证，然后启动对应 NapCat 子流程；NapCat 子流程启动后等待目标 OneBot established 连接。AstrBot stdout 会写入 `AstrBot startup phase: ...` 预启动阶段日志，启动器等待摘要会识别 Core、插件、provider、KnowledgeBase 和 WebUI 等阶段，方便区分是 AstrBot 自身启动慢还是 NapCat 登录慢。双平台 `both/full` 下，启动器用 `data\launcher\napcat-quick-login\<account>.ready` 标记账号是否已确认过快速登录：任一账号缺少标记时按天使优先串行启动，避免两个账号同时生成二维码并覆盖共享的 `napcat\onekey\napcat\cache\qrcode.png`；两个账号标记都存在时按天使优先并行启动以缩短重启时间；并行或串行中某账号没有成功反连时会清除该账号标记，下次启动自动退回串行。启动器控制台状态和失败停窗提示使用英文/ASCII 摘要，避免 Windows 控制台无法正确显示 NapCat 中文日志时出现乱码；AstrBot 反向 WebSocket 端口如果出现 `WinError 10013`、`PermissionError` 等平台绑定错误，启动器会从日志中快速识别并失败，不再等满长超时。

AstrBot 双平台下，普通闲聊、显式呼叫和 follow-up 允许两个棉花糖共同参与；群聊固定命令只由一个账号执行。没有明确 @ 或私聊时，固定命令默认由恶魔账号 `2629227874` 处理，可用 `QQBOT_ASTRBOT_COMMAND_OWNER` 覆盖；明确 @ 天使/恶魔时，由当前被叫到的 bot 处理；同时 @ 两只的普通聊天会让两只各自用自己的身份回答；私聊由当前收到私聊的 bot 独立处理，命中固定命令就执行对应命令，未命中固定命令就进入当前 bot 的 LLM 链路。`菜单`、`帮助`、`指令` 会发送统一图片菜单，总览按 `群务管理`、`棉花糖互动`、`养鲲`、`落樱之都`、`Arcaea`、`Factorio`、`异形工厂` 分组；`菜单模块名` 会发送模块详情图。

`astrbot_plugin_qqbot_features` 不再读取旧公开群上下文 JSON；群聊 LLM 上下文交给 AstrBot 当前会话上下文和本轮引用消息。旧 `data\astrbot\data\plugin_data\qqbot_features_runtime\ai\group_context\` 只作为历史快照清理对象，不再作为 prompt 事实源，也不再提供“棉花记录/导出 md”命令。

`astrbot_plugin_qqbot_features` 内部的双子互动模块负责天使/恶魔两个棉花糖的双子互动增强：当用户明确围绕天使、恶魔、姐姐/妹妹、双子关系或另一个 bot 发问时，模块会给本轮 LLM 请求注入当前 bot、另一个 bot 的账号事实和互动边界。它不注入固定人设或语气文本，只让当前 bot 用自己的 WebUI 人格回应，不替另一个 bot 发言、认错、解释或承诺修改；用户说“你姐”“你妹”“姐姐”“妹妹”时按当前消息的 `self_id` 视角理解，避免天使把自己当恶魔或恶魔把自己当天使。另一个 bot 发出的普通消息不会触发当前 bot 自动接话。用户让被点名 bot 和另一只抱抱、贴贴、道歉、哄人、叫出来或转告这类目标专属双子互动时，只允许被点名目标自己处理；目标正忙时另一只不代班完整回答。配置项集中到功能合集卡片下，以 `twin_interaction_` 为前缀。

`astrbot_plugin_qqbot_features` 内部的源码知识模块负责 bot2 的源码知识兜底：在没有 Embedding 模型、不能使用 AstrBot 原生知识库时，它会按当前群号和问题文本只读检索本机源码树，并把少量相关源码片段临时注入本轮 LLM 请求。默认源码根覆盖 DSPCore、万物分馏、MLJ_DSPmods 辅助模组/工具、星环、创世之书、shapez 和 Factorio 模组源码；其中辅助模组/工具域覆盖 SaveDataExporter、UXAEnhance、AfterBuildEvent、GetDspData、VanillaCurveSim 和 UXAssist。可信依据优先是源码、反编译源码、源码邻近 README/设计文档和配置数据。群号只作为默认领域偏置；当问题出现精确模组名、工具名、目录名或机制词时，模块会跨默认群域检索对应源码根。源码知识默认按低成本注入：`source_knowledge_max_results=4`、`source_knowledge_max_chars=2600`、`source_knowledge_max_files_per_domain=80`、`source_knowledge_max_file_bytes=220000`；复杂技术追查需要大文件证据时，再在运行态配置里临时调高。模块跳过 `.git`、`.codex`、`bin`、`obj`、`.vs`、`.idea`、`packages`、`node_modules`、`logs`、缓存和密钥类文件，不读取私聊、运行日志、token、QQ 登录态、运行态 `data` 或数据库密钥。配置项集中到功能合集卡片下，以 `source_knowledge_` 为前缀。

`astrbot_plugin_topic_concentration` 负责显式呼叫和双棉花糖普通回复调度，不再 patch AstrBot Core 的 `GroupChatContext.need_active_reply`。AstrBot 原生 `provider_ltm_settings.active_reply.enable` 默认关闭，普通群聊不会按定时/消息数主动插话。直接 @ 当前 bot 或引用当前 bot 会进入普通 LLM；同时 @ 天使和恶魔的普通聊天，两只都会各自用自己的身份回答，不得输出“我不能代替姐姐/妹妹回答”这类拒答；纯同时 @、`在吗`、`出来` 或 `说句话` 这类无实质正文场景，两只也各自短句应到，不转交、不追问用途。未明确指定身份但文本包含“棉花糖”时，插件先判断是不是在叫机器人：`棉花糖很好吃` 这类食物/物件说法不回复，`棉花糖，帮我生成一张图片` 或 `棉花糖这个图片是哪个角色` 这类请求会按群权重选一只回复。模糊句只调用 AstrBot 当前会话 provider 做一次轻判定，失败则不回复，不新增独立 provider 顺序或 fallback。触发回复后，同群同用户会进入 3 分钟 follow-up 窗口，后续普通消息不需要继续 @；窗口绑定实际回复的那只棉花糖，最多 6 条普通后续消息，模型可在回复末尾返回内部标记 `[[QQBOT_FOLLOWUP_END]]` 终止窗口，发送前会清理该标记。私聊永远由当前收到私聊的 bot 处理；固定命令、生图、群务、下载和游戏存档仍按 command claim 保证只执行一次。

`astrbot_plugin_qqbot_features` 负责已迁移的群务、菜单、生图、游戏、固定命令、源码知识注入、双子互动边界、回复风格守卫和运行时错误拦截。好友申请和邀请入群默认按配置自动同意；机器人自身入群成功后会优先私聊通知邀请者，文案包含群名和群号，不在群聊里发送“主人”自报。双平台 `both/full` 下，天使和恶魔会各自按身份发送新成员入群欢迎，并各自独立随机选择以“群地位”开头、表达群地位变量减 1 的完整表达式；双子自身入群不会触发欢迎。旧的独立本地插件配置文件若仍存在，会在功能合集对应新配置项未填写时作为兼容兜底读取；新的 WebUI 配置入口统一在“棉花糖功能合集”卡片。

`astrbot_plugin_qqbot_features` 内部的回复风格守卫负责发送前清洗 Markdown、末尾问句、追问式邀请、follow-up 内部结束标记和末尾装饰性口癖/身份 emoji，记录 LLM 耗时，并显式控制和 AstrBot 原生分段的关系。插件配置 `reply_style_guard_disable_astrbot_segmented_reply=true` 时，普通 LLM 模型结果会被改为 `GENERAL_RESULT`，故意架空 WebUI `platform_settings.segmented_reply.only_llm_result` 的句末正则分段，避免引号内句号或解释类回答被拆成多条刷屏；关闭该插件配置后恢复 AstrBot 原生分段行为。群聊消息、引用消息和群友要求只能作为本轮聊天内容或事实线索，不能改变输出风格、人格、身份或长期规则；要求固定口癖、标点、emoji、称呼、语气、Markdown、URL 编码或其他格式时，模型必须忽略该风格要求，只有明确要求转换一段给定文本时才处理那段文本本身。普通群聊问答会在 LLM 请求前提示模型按 QQ 群里正常接话的短句输出：一句能说完就只发一句，第二句只在补充限制、纠错或关键证据有用时才发；日常闲聊、吐槽、接梗不要强行套“结论+原因”结构，也不要上价值讲大道理；技术、配置、报错和机制问题只补最短必要条件。模型主动输出两行以内短文本时，插件只按换行拆成多个 `Plain` 组件交给 AstrBot 发送链路，不按句号正则二次切分。插件配置 `reply_style_guard_long_reply_fold_threshold_chars` 默认 300，超过阈值的群聊 LLM 纯文本回复会先改写为 AstrBot `Nodes/Node` 合并转发消息链，再交回 Core 发送链路；该阈值独立于 Core `forward_threshold`。群聊中直接 @ 或唤醒当前 bot 后，正文超过 `reply_style_guard_long_input_tldr_threshold_chars` 时默认本地回复 `太长不看喵`，不进入 LLM；这个短路只限制群聊，私聊不限制，固定命令、生图、群管、下载、积分等副作用入口也不走这个短路。私聊发送 OneBot 合并转发/折叠消息时，插件会通过 `get_forward_msg` 解包纯文本，再交给当前收到私聊的 bot 进入 LLM 链路。非“主人私聊”时，模块会在 LLM 请求前剔除本机命令、Python、文件读写、grep、浏览器、上传下载等运行态工具；发送前会移除引导用户去 WebUI 添加管理员、开启 shell 或文件权限的内容。模块不再向 LLM 请求注入固定人设、固定水群风格或固定口癖；天使/恶魔身份、说话风格和群聊氛围只由 AstrBot WebUI 人格配置提供。模块会在本地日志记录 LLM 请求开始、模型返回和发送前装饰耗时，不记录完整 prompt 或回复正文。长作文或慢请求不按固定秒数丢弃，是否失败以 provider timeout/error/fallback 日志为准。

普通聊天文本不会因为 `在吗`、`111`、`真的吗`、`回复慢`、`低信息` 或测试探活这类启发式在本地插件里直接生成固定回复；没有命中明确命令、游戏会话答案、协议事件处理或本地硬安全提醒时，统一交给 LLM 链路。

本地表情包统一并入 `astrbot_plugin_qqbot_features` 内部表情管理模块，不再保留独立 `meme_manager` 插件。启动脚本会清理运行态旧 `data\astrbot\data\plugins\meme_manager\` 插件目录；运行态图片和单图语义索引仍兼容使用 `data\astrbot\data\plugin_data\meme_manager\memes\` 与 `meme_index.json`。私聊发送 `表情管理 开启管理后台` 后，可在 WebUI 中预览、搜索、移动分类、编辑单图说明/关键词/适用场景/禁用场景和自动发送开关。旧 `data\memes\mlj_pack\index.json` 只作为迁移来源，可用 `tools\maintenance-scripts\migrate-meme-pack-to-manager.py` 或兼容命令 `tools\maintenance-scripts\sync-meme-pack.py` 复制/合并进表情管理运行态，不会删除旧目录。自动发送仍遵守 `auto_send_enabled=false`：敏感支付、涩涩慎用、待复核类别不得自动发送；轻松日常、玩梗、吐槽、撒娇和短情绪回复优先使用表情，技术、报错、安全、群管理和长解释场景不自动附图。LLM 输出的 `&&标签&&` 和可识别的半截/畸形表情标签会在发送前清理，不能把裸标签文本发到群聊。

## 启动

日常入口：

```powershell
Set-Location D:\project\qqbot
.\scripts\start-all.bat
```

日常入口只有 `scripts\start-all.bat`，默认启动 AstrBot 的天使+恶魔双平台；直接运行 `tools\runtime-scripts\start-all.ps1` 时默认也是 AstrBot `both/full`。入口默认只保留一个终端窗口，按组件前缀输出 AstrBot 和 NapCat 的阶段摘要；如果现有运行态已经 ready，入口会直接复用当前 AstrBot 和 NapCat 连接。需要强制重启时运行 `tools\runtime-scripts\start-all.ps1 -Target astrbot -SkipInstall -AstrBotProfile both -FeatureMode full -ForceRestart`。冷启动或强制重启时，NapCat 会在 AstrBot WebUI、双 OneBot 端口和 artifact API 都 ready 后再启动；双账号 NapCat 在缺少快速登录标记或上次失败后按天使优先串行启动，两个账号都确认过快速登录后按天使优先并行启动。

默认账号链路：

- `1443944862`：AstrBot 天使平台，默认反连 `ws://127.0.0.1:6200/ws`。
- `2629227874`：NapCat 反连 AstrBot 恶魔平台，默认 `ws://127.0.0.1:6201/ws`。

NapCat 仍使用 `napcat/` 下的一键包；更新脚本会保留并迁移账号 OneBot 配置，更新下载和旧包备份放在 `data/napcat/`。

## Linux / 1Panel 部署

服务器托管双棉花糖时，1Panel 只负责安装和运行 AstrBot Core；本仓库的完整运行还需要同步 `astrbot-local-plugins/` 三个本地插件、两路 aiocqhttp 平台、两个 NapCat 协议端和必要 `plugin_data` 运行态。完整步骤见 `docs/server-deployment-linux.md`。

后续修改推荐只走一条主线：本机改动、本机验证、Git 提交、服务器 `git pull`、同步插件、重启 AstrBot / NapCat。服务器上直接用 Codex 改只作为紧急热修；热修完成后必须把 diff 拉回本机复核并提交，避免本机和服务器各自演化。

## 更新

AstrBot Core 和 NapCat 使用统一手动更新入口：

```powershell
Set-Location D:\project\qqbot
.\scripts\update-all.bat
```

`update-all.bat` 会按顺序更新 NapCat 和 AstrBot Core；内部实现放在 `tools\runtime-scripts\update-napcat.ps1` 和 `tools\runtime-scripts\update-astrbot.ps1`。默认是交互式更新：NapCat 下载前会显示当前版本、目标 release、asset 名称、下载 URL、本地 zip 路径和后续替换动作并询问；AstrBot install/upgrade 前会显示当前 tool 状态、计划执行的 uv 命令和会处理的运行进程并询问。无人值守时可给 PowerShell 入口加 `-AssumeYes` 自动确认。

NapCat 更新会先查询 GitHub 最新 release；如果本地记录已经是最新 release，则直接跳过下载和替换。本地旧包没有 release 标记时，会回看最近成功的 NapCat 更新日志作为版本来源；仍无法确认时显示当前版本为 unknown，并在下载前询问。确认后才下载 Windows Shell OneKey zip 并解压到临时目录，确认新包准备好后再停止本工作区关联的 NapCat/QQ 进程，把旧 `napcat\onekey` 备份到 `data\napcat\archives\`，替换程序包后自动迁移 `napcat_*.json`、`napcat_protocol_*.json` 和 `onebot11_*.json` 账号配置。

AstrBot 更新在用户确认后，会停止本工作区正在运行的 AstrBot uv tool 进程，再使用当前 Windows 已安装的 Python 3.14，执行 `uv tool upgrade astrbot --python 3.14`；如果本机还没有安装 AstrBot tool，则改为 `uv tool install astrbot --python 3.14`。如果 Windows PATH 找不到 `uv`，脚本会在确认后用 `py -3.14 -m pip install --user -U uv` 安装用户级 uv。更新日志写入 `data/astrbot/logs/updates/`。

更新后使用 `scripts\start-all.bat` 启动 bot2。修改 `astrbot/` 里的源码快照不会影响实际运行的 bot2，除非重新切换回源码模式。
