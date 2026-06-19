# AGENTS.md - QQBot Monorepo 工作流程

本仓库是机器人运行工作区，包含多个应用和共用协议端。

## 基本原则

- 默认使用简体中文沟通。
- 修改前先确认目标子目录：`astrbot/`、`astrbot-local-plugins/`、`napcat/`、`scripts/`、`tools/`、`data/`。
- 不把真实 token、QQ 登录态、数据库、运行日志或本机配置提交进 Git。
- 完成可验证改动后需要提交，除非用户明确要求暂不提交。
- 严禁 push，除非用户明确批准。

## 目录边界

- `astrbot/`：AstrBot 上游源码快照和本机配置示例；不保留 AstrBot 上游 Git 历史，也不作为 bot2 Core 的日常启动来源。
- AstrBot 行为调整硬限制：配置优先，插件其次，绝不直接修改 AstrBot Core 源码。能通过 `data/astrbot/data/` 运行态配置、AstrBot 参数或插件实现的行为，不允许改 `astrbot/` 源码快照或 uv tool 安装目录源码；只有先确认配置和插件都无法实现，并获得用户明确批准后，才允许讨论 Core 补丁。新增、改造或迁移 AstrBot 插件能力前，必须先查 AstrBot 原生配置、WebUI 现有开关、Core 已有行为和本仓库现有插件是否已经提供同类能力；若 AstrBot 原生能力可满足或可复用，应优先复用并只做最小插件补足。若原生能力语义不符合本仓库需求，可以在插件中显式架空或覆盖，但必须在插件配置 schema、README/AGENTS、日志或配置说明里写清楚覆盖了哪个原生设置、默认值、恢复原生行为的方法和冲突风险；禁止无说明地另起一套会和原生设置冲突、重复或绕过原生配置的开关、provider、分段、路由、权限或发送机制。
- `astrbot-local-plugins/`：本仓库维护的 AstrBot 本地插件源码；`tools/runtime-scripts/start-astrbot.ps1` 启动前同步到 `data/astrbot/data/plugins/`。新增或迁移 bot2 功能时优先放这里，避免直接修改 `astrbot/` Core 源码或把 `data/` 运行态纳入 Git。
- 原 qqbot / NoneBot2 功能已迁入 AstrBot 本地插件；运行时代码不得依赖 `nonebot2/` 源码、`nonebot` 包、NoneBot2 plugin 入口或 OneBot adapter。
- 从旧 qqbot 迁入的纯 Python service 只允许作为 AstrBot 插件内 vendored service 使用，运行态数据根统一为 `data\astrbot\data\plugin_data\qqbot_features_runtime`，迁移配置根统一为 `data\astrbot\data\plugin_data\qqbot_features_config`。
- AstrBot 账号/身份切换通过启动参数显式控制：日常默认是 `-Target astrbot -FeatureMode full -AstrBotProfile both`，在同一个 AstrBot 管理端内同步两个 `aiocqhttp` 平台，恶魔默认反连 `6200`，天使默认反连 `6201`，并分别拉起两个 NapCat 账号；显式 `-AstrBotProfile demon` 才使用恶魔账号 `2629227874` 单平台，显式 `-AstrBotProfile angel -FeatureMode full -Target astrbot` 才使用天使账号 `1443944862` 单平台。本地插件必须按事件 `self_id` 区分天使/恶魔身份，不能把 `QQBOT_ASTRBOT_PROFILE` 当成双平台模式下的单一身份事实源。AstrBot OneBot 恶魔端口可用 `-AstrBotOneBotPort` 覆盖，天使端口可用 `-AstrBotAngelOneBotPort` 覆盖；不要重新硬编码 `6199`。
- AstrBot provider 选择、模型切换和回退链只归 AstrBot Core / 会话配置 / `provider_settings` 管理，本地插件不得再实现独立 provider 顺序、独立 fallback 或“判定专用模型”配置。`astrbot_plugin_topic_concentration` 负责主动接话前的窗口、批量话题归类、去重、冷却、双 bot 消息过滤、按群调度权重和普通 LLM worker 调度；它启动时显式 patch `GroupChatContext.need_active_reply`，只覆盖 `active_reply.method=possibility_reply` 的主动接话判定，其他 method 必须回落 Core 原逻辑，Core 签名不兼容时不得安装 patch 并必须记录 ERROR 日志。普通主动接话不再逐消息调用 LLM 判定，只有普通群聊窗口达到批量时间或消息数门槛后，才用 AstrBot 当前会话正在使用的 provider 做一次批量归类，失败则静默跳过本批次，不在插件里切换模型；所有主动接话批量判定结果包括 `should_reply=false` 必须记录 INFO 日志。普通主动接话窗口如果依赖图片、视频、表情、卡片或转发内容，但当前只有 `[图片]` 这类占位、没有可用文字描述或引用文本，必须静默跳过，不能让 LLM 猜图中物品、升级、价格、界面或报错；明确 @、引用当前 bot、私聊和命名呼叫不受该普通主动接话批量门槛影响。明确出现“棉花糖”“棉花糖在吗”“呼叫棉花糖”或“棉花糖+明确请求”等命名呼叫时，本地门控应直接选择一个普通 LLM worker 并放行，不依赖主动接话判定 provider；同一用户短时间内紧接“在吗”等探活短句也继承这次呼叫。
- AstrBot 好友申请和邀请入群由 `astrbot_plugin_qqbot_features` 处理：默认通过 `auto_approve_friend_requests` 和 `auto_approve_group_invites` 自动同意 OneBot `friend` 请求与 `group/invite` 请求，并记录 action、flag、sub_type 和失败原因；机器人自身入群成功后私聊通知邀请者，文案包含群名和群号，不能在群聊里发送“主人”固定自报；双平台 `both/full` 下天使和恶魔各自按 `self_id` 发送不同的新成员入群欢迎，并各自独立随机选择以“群地位”开头、表达群地位变量减 1 的完整表达式，双子自身入群不触发欢迎；不允许把邀请入群问题交给 LLM 解释成“机器人不能自己加群”。
- RightCodes 生图命令入口归入 `astrbot_plugin_qqbot_features`，不再新增独立固定命令插件；默认使用 `data\astrbot\data\plugin_data\qqbot_features_runtime\ai\draw_points.json` 积分存档。积分事实源只保留当前积分和当天免费次数状态，不保留历史累计消息数或 `message_count` 字段。RightCodes API Key 归 AstrBot 插件配置 `astrbot_plugin_qqbot_features.api_key`，直接在 WebUI/运行态插件配置填写；插件不得再读取 `QQBOT_AI_KEY_RIGHTCODES` 或旧 `.env` 作为生图 key 来源。AstrBot 负责普通群消息积分累计；双平台 `both/full` 下只有固定命令 owner 账号累计普通群消息积分，避免天使和恶魔同群时同一消息重复记分。生图成功、失败或超时失败必须引用原始生图请求；失败和超时失败必须退回已扣积分或当天免费次数。
- RightCodes 生图接口知识也归入 `astrbot_plugin_qqbot_features` 的静态 catalog，不新增独立插件；用户问画图接口、请求体、`size`、`1024x1024`、`/v1/images/generations` 或 `/v1/chat/completions` 时，LLM 请求前应注入官方文档摘要。`/v1/images/generations` 明确支持 `size` 字段；`/v1/chat/completions` 适合流式防 Cloudflare 超时，但尺寸控制应写进文本提示。
- 公开群上下文桥接优先用 AstrBot 本地插件实现，不改 Core。桥接插件只能只读 `data\astrbot\data\plugin_data\qqbot_features_runtime\ai\group_context\` 这类公开群上下文，默认不按具体群号限制；星环群 `1035445959` 只能作为领域提示特例，不能作为桥接范围条件。不得读取私聊、token、QQ 登录态、数据库密钥或运行日志作为 LLM prompt 证据。
- 双子 bot 互动由 `astrbot_plugin_qqbot_features` 内部的双子互动模块负责，只在用户明确围绕天使/恶魔/双子关系或另一个 bot 公开输出发问时增强当前 bot 的 LLM 上下文或接管明确请求。它必须按事件 `self_id` 注入当前 bot 动态身份事实，用户说“你姐”“你妹”“姐姐”“妹妹”时必须按当前 bot 视角理解，不能让天使把自己当恶魔、恶魔把自己当天使。它不得响应另一个 bot 发出的普通消息，不得冒充另一个 bot 发言、替另一个 bot 认错、解释或承诺修改；调度层安排普通 LLM 代班/接力时，当前 bot 只能用自己的身份处理。近期上下文只能只读公开群上下文文件，不得读取私聊、日志、token、QQ 登录态或数据库密钥。
- AstrBot 源码知识兜底优先用 `astrbot_plugin_qqbot_features` 内部的源码知识模块实现，不改 Core、不依赖 Embedding。可信依据必须优先来自源码、反编译源码、源码邻近 README/设计文档和配置数据，尤其是戴森球计划本体相关源码、相关 mod 源码和 MLJ_DSPmods 辅助模组/工具资料；群聊、群文件、攻略和 release notes 只能作为候选或补充。群号只能作为默认领域偏置，不能当成唯一领域事实；分馏群、星环群也可能问同一 DSP 工作区里的其他模组或工具，精确模组名、工具名、目录名和机制词应优先触发跨默认群域检索。源码检索模块只读明确配置的源码根，必须跳过 `.git`、`.codex`、`bin`、`obj`、`.vs`、`.idea`、`packages`、`node_modules`、`logs`、缓存和密钥类文件；不得读取私聊、token、QQ 登录态、数据库密钥、运行日志或本仓库运行态 `data`。为保证大号源码邻近说明文件可召回，`source_knowledge_max_results`、`source_knowledge_max_chars`、`source_knowledge_max_file_bytes` 不能配置得低于插件有效下限。
- 双平台共用 AstrBot 本地插件 `meme_manager` 的本地表情包索引，运行态事实源是 `data\astrbot\data\plugin_data\meme_manager\meme_index.json` 和 `memes\`，插件源码事实源是 `astrbot-local-plugins\meme_manager\`，启动前同步到 `data\astrbot\data\plugins\meme_manager\`；`data\memes\mlj_pack\index.json` 只作为历史迁移来源保留，不再作为日常运行事实源。轻松日常、玩梗、吐槽、撒娇和短情绪回复应优先使用表情，短情绪闲聊允许纯表情回复，`auto_send_enabled=false` 的敏感支付、涩涩慎用、待复核类别不得自动发送。`meme_manager` 通过 `/表情管理 开启管理后台` 提供本地图库 UI，支持预览、搜索、分类移动、类别编辑、单图说明/关键词/适用场景/禁用场景和自动发送开关；发送链路不额外调用 LLM 做单图选择，只让主 LLM 决定是否用表情和粗类别，再由插件本地 selector 按类别、关键词、禁用场景、权重和近期去重选图。不改 Core、不删除旧图库目录；`tools\maintenance-scripts\migrate-meme-pack-to-manager.py` 和兼容命令 `tools\maintenance-scripts\sync-meme-pack.py` 只做旧 `mlj_pack` 到 `meme_manager` 的复制/合并迁移。
- 本地 artifact 发布迁移到 `astrbot_plugin_local_artifact_api`，在 AstrBot `full` 模式下监听 `127.0.0.1:8080` 的兼容 `POST /admin/api/artifacts/publish-local`；它使用插件内发布服务和 `data\astrbot\data\plugin_data\qqbot_features_runtime` 发布状态，通过 AstrBot aiocqhttp OneBot 上传群文件，不改 AstrBot Core。发布服务必须独立打开 zip 计算内容 hash，与自身缓存比对后再决定是否删除、上传和发群消息；客户端传入的 `content_sha256` 只能用于一致性校验，不能作为唯一判重事实源。AstrBot-only 启动会清理旧 8080 占用并接管该端口。
- AstrBot `full` 模式启动验证必须同时覆盖 WebUI `6185`、OneBot `6200/6201` 和 artifact API `8080`；`LocalArtifactApi failed to listen`、`WinError 10013` 或 `PermissionError` 不能被当成 ready 状态忽略。
- 双平台运行时，普通主动接话不得由另一个 bot 的普通输出继续触发；普通群聊主动接话判定必须按群做 in-flight 门控，避免上游慢或超时时多个旧主动回复结果一起返回刷屏。明确 @、引用当前 bot、命名呼叫和主动接话这类普通 LLM 请求进入双 worker 调度：目标 bot 空闲时由目标处理，目标 bot 正在等待 LLM 返回时可由另一个 bot 用自己的身份代班/接力；代班 worker 一旦开始处理，原目标 bot 必须抑制对原消息的完整回答，等代班回复公开后只做一句基于原消息和代班回复的实质短评论，不能说“接住/我看到了/已经处理啦”这类空话。私聊永远由当前收到私聊的 bot 处理，不参与跨 bot 随机 worker、claim 或忙闲代班；私聊命中固定命令时执行当前 bot 的对应命令，未命中固定命令时一定进入当前 bot 的 LLM 链路。固定命令、权限动作、扣积分、写文件、上传、群管、下载和游戏存档只参与“唯一执行者选择”和 command claim 去重，不参与普通 LLM 代班；其中私聊 command claim 必须按当前 `self_id` 隔离，不能让天使和恶魔互相去重。两个 bot 的普通回复、主动回复和拒答都不要反问，不要用“如果你愿意”“要的话”“你把具体名字发我”“我可以再帮你”等追问式收尾；缺关键信息时陈述缺口，不催用户补充。
- 双平台普通回复、主动回复和拒答必须使用 QQ 纯文本风格，禁止输出 Markdown 语法；不得使用 `#` 标题、`-` 或 `*` Markdown 列表、`**粗体**`、反引号代码块、`>` 引用、Markdown 链接或表格。回答 API、JSON、请求体、配置时允许保留换行和缩进，但不要使用 Markdown 代码围栏。AstrBot 侧由 `astrbot_plugin_qqbot_features` 内部回复风格守卫在 LLM 请求前提示并在发送前清洗，同时记录 LLM 请求开始、模型返回和发送前装饰耗时；耗时日志不得记录完整 prompt 或回复正文。普通 LLM 模型结果默认由插件配置 `reply_style_guard_disable_astrbot_segmented_reply=true` 架空 AstrBot 句末正则分段，避免引号内句号或解释类回答被拆成多条刷屏；这是显式插件覆盖，关闭该配置后恢复 AstrBot WebUI 原生分段。普通群聊问答优先让 LLM 直接输出一到两行短气泡：第一行给结论，第二行只放必要证据、条件或纠错；插件只按模型明确输出的两行以内短文本拆成多个 `Plain` 组件交给 AstrBot 发送链路，不按句号正则二次切分。插件配置 `reply_style_guard_long_reply_fold_threshold_chars` 默认 300，超过阈值的群聊 LLM 纯文本回复会被改写为 AstrBot `Nodes/Node` 合并转发消息链并交回 Core 发送链路；该阈值独立于 Core `forward_threshold`。群聊中直接 @ 或唤醒当前 bot 后，正文超过 `reply_style_guard_long_input_tldr_threshold_chars` 时默认本地回复 `reply_style_guard_long_input_tldr_text`（`太长不看喵`），不进入 LLM；这个短路只限制群聊，私聊不限制，固定命令、生图、群管、下载、积分等副作用入口也不走这个短路。私聊 OneBot 合并转发/折叠消息必须通过 `get_forward_msg` 解包纯文本后交给当前收到私聊的 bot 进入 LLM 链路。固定命令和插件手写多条发送不受 LLM 分段覆盖影响。长作文或慢请求不能按固定秒数丢弃，非流式请求是否失败以 provider timeout、HTTP 错误和 fallback 日志为准。
- AstrBot 本机运行态工具只允许主人 `605738729` 的私聊保留；群聊和普通用户私聊必须在 LLM 请求前剔除命令行、Python、文件读写、grep、浏览器、上传下载等本机工具。LLM 不得引导群友去 WebUI 添加管理员、开启 shell 权限、文件权限或后台权限；需要写文件的固定能力必须做成受控插件命令，使用固定安全目录和程序生成文件名，不接受用户路径。
- 群聊记录导出由 `astrbot_plugin_qqbot_features` 的主人限定固定命令处理，只读公开群上下文 `data\astrbot\data\plugin_data\qqbot_features_runtime\ai\group_context\<群号>.json`，只写 `data\astrbot\data\exports\group_notes\`，不得读取私聊、运行日志、token、QQ 登录态、数据库密钥，也不得让 LLM 通过 shell 自行写“当前目录”。
- AstrBot 双平台 `both/full` 下，闲聊、普通问答和主动接话可以由两个 bot 按 worker 调度策略共同参与；同一群维护一个调度 `balance`，数值越大越偏向天使、越负越偏向恶魔，但只是概率偏置，不能变成必然选择。未明确指定天使/恶魔的固定命令按群权重选一个执行者；同时 @ 双方的固定命令也只选一个执行，另一只最多发短状态评论；同时 @ 双方的普通聊天允许两只各自用自己的身份回答，并注入“用户同时叫了两个人”的上下文；用户同时对两只表达喜欢、感谢、夸奖或吐槽时，每只只能代表当前 bot 独立回应，不能替另一个 bot 接受、感谢、道歉、承诺或猜测对方心情。群聊固定命令必须按目标 @、按群权重和 canonical claim 唯一执行；claim key 优先使用群号、发送者、当前纯文本、@ 目标、引用消息和时间桶，不依赖双平台可能不一致的 message_id；引用消息优先使用引用正文摘要，只有没有引用正文时才退回平台 reply_id，避免同一条引用消息在天使/恶魔两路产生不同 claim。私聊固定命令按当前 `self_id` 独立执行，不和另一只 bot 共享去重 claim。菜单、帮助、指令、生图、下载、群文件清理等固定命令不得因双平台群聊重复执行。AI 或普通 LLM 判定“像固定功能”的自然语言请求只能提示真实指令和消耗/副作用，不能直接执行扣积分、写文件、上传、群管、下载或改存档。
- 普通聊天文本不得在 AstrBot 本地插件里按“低信息、在吗、111、真的吗、回复慢、测试、探活”等启发式直接生成本地回复；只要没有命中明确命令、游戏会话答案、协议事件处理或本地硬安全提醒，就必须交给 LLM 链路处理。插件可以做 prompt 注入、上下文桥接、记忆检索、输出清洗和路由门控，但不能凭空补一句固定兜底文本。
- 双平台所有群聊和私聊 LLM 回复都不做危机处理；自述、倒霉、考试迟到、没吃饭、没睡觉等默认按玩笑、夸张、钓机器人或时间梗分析。分析不出发言原因时不回答，不编原因，不输出危机干预、急救、报警、健康建议或严肃安慰；凭据泄露等本地硬安全提醒仍按既有规则执行。
- 双平台不保留“严肃模式”人格切换；所有群聊都按轻松水群氛围处理。技术、代码、报错、配置、群管理和安全提醒也必须保持当前天使/恶魔人设语气，但结论要准确、可执行，不能用卖萌或吐槽遮住关键信息。复读、频繁艾特、怪图/表情包和深夜修仙默认是水群行为，直接被叫到时短句接梗、安慰或吐槽；普通主动接话窗口里不要因此刷屏。恶魔棉花糖平时不主动使用固定“喵”口癖，不要写“哼...喵”这类模板化短口癖。AstrBot 侧天使/恶魔身份、人设、说话风格和双子关系只来自 AstrBot WebUI 人格配置（运行态 `data\astrbot\data\data_v4.db`）；本地插件不得内嵌或覆盖固定人格、水群风格或固定口癖，只能注入动态事实、公开上下文、接口资料、权限边界和 QQ 纯文本/短气泡这类格式边界。
- `napcat/`：共用 NapCat 程序包；更新下载和旧包备份应放在 `data/napcat/`，当前账号 OneBot 配置随一键包放置并由更新脚本迁移。
- `data/`：统一运行态根目录，默认忽略，不进 Git。
- `scripts/`：只保留 `start-all.bat` 和 `update-all.bat` 两个根级 Windows 用户入口。
- `tools/runtime-scripts/`：`scripts/` 两个 all 入口调用的内部 PowerShell 启动、重启和更新实现。
- `tools/maintenance-scripts/`：配置示例导出、表情迁移等非日常维护脚本。

## 配置示例导出

- AstrBot 可提交配置示例放在 `astrbot/config/`；当前运行态配置导出入口是 `python3 tools/maintenance-scripts/export-astrbot-config-examples.py`。
- 导出脚本可读取 `data\astrbot\data\cmd_config.json`、`data\astrbot\data\config\*.json` 和 `data\astrbot\data\data_v4.db` 的 personas 表；输出前必须剔除 LLM provider/model/provider_sources/provider_settings/fallback/image-caption/embedding 路由，并脱敏 key、token、secret、password、cookie、authorization、custom headers/body 等字段。
- example 可以保留非密钥运行形态，例如端口、bot 账号、群号、插件开关、功能模式和人格文本；不得提交真实 provider key、OneBot token、登录态、数据库密钥、运行日志或会话历史。

## 数据路径

- AstrBot 启动时应设置：
  - `ASTRBOT_ROOT=D:\project\qqbot\data\astrbot`
  - AstrBot 实际数据目录为 `D:\project\qqbot\data\astrbot\data`
  - 迁移功能运行态数据为 `D:\project\qqbot\data\astrbot\data\plugin_data\qqbot_features_runtime`
  - 迁移功能配置为 `D:\project\qqbot\data\astrbot\data\plugin_data\qqbot_features_config`
  - Core 由 `uv tool` 管理，启动脚本调用 `astrbot run -p 6185` 或 `uv tool run --from astrbot --python 3.14 astrbot run -p 6185`

## 验证

- 结构变更后至少检查：
  - `git status --short`
  - 根目录是否只有一个 `.git`
  - `data/` 是否未进入 Git
- 根目录 `tests/` 保留 AstrBot 本地插件、启动脚本和配置导出回归测试；相关改动优先运行 `py -3.14 -m pytest tests` 或本机可用的等价 Python 命令。
- AstrBot Core 源码快照不作为运行态；Core 相关验证优先使用 ruff、`python -m py_compile` 和实际 uv tool 启动探针。
- AstrBot Core 运行/更新脚本变更优先做 PowerShell 语法检查；不要把源码快照测试结果当作 uv tool 运行态验证。
- 修改 AstrBot persona、插件注入提示词、回复风格守卫、LLM 路由提示、主动接话判定提示、源码知识或接口资料注入等会影响模型输出的 prompt 后，必须使用实际运行配置对应的 AI/provider 接口做真实模拟调用，样例至少覆盖本次变更目标场景；验证记录必须包含关键输入、实际模型输出、provider/model 和判断结论。允许直接调用对应 AI 接口完成验证，不能只靠想象、静态阅读或未调用模型就声称回答符合预期。
- 对本仓库启动、重启、更新、进程残留、端口占用、脚本编排和机器人运行态修复，完成脚本或配置改动后必须直接执行真实入口验证；不要因为会停止现有机器人、关闭 NapCat/QQ、替换 `napcat\onekey`、升级 uv tool、重启 AstrBot、清理残留进程或短暂中断服务而停下来要求用户再次确认。用户提出这类问题本身即表示要解决到真实运行可用。

## 启动与重启

- 日常启动入口是 `D:\project\qqbot\scripts\start-all.bat`，默认启动 AstrBot 天使+恶魔双平台。
- 修改会影响正在运行机器人的代码、配置、提示词、运行包或启动脚本后，必须重启对应机器人并做启动验证；不能只停在“已修改/已提交”。若当前环境无法重启，最终回复必须明确写出未重启、原因和应执行的入口。
- 只影响 AstrBot Core、`data\astrbot\data\cmd_config.json`、AstrBot persona 或 uv tool 运行包的改动，重启 bot2：`scripts\start-all.bat`；该入口默认以 `-AstrBotProfile both -FeatureMode full` 启动同一管理端内的天使+恶魔双平台。
- AstrBot 接管已迁移自动事件时，使用 `scripts\start-all.bat` 或显式 `tools\runtime-scripts\start-all.ps1 -Target astrbot -SkipInstall -AstrBotProfile both -FeatureMode full`。如本机端口冲突，可加 `-AstrBotOneBotPort <端口>` 和 `-AstrBotAngelOneBotPort <端口>` 同步 AstrBot 和 NapCat 反连配置。
- 需要 NapCat 重新反连时也使用普通 AstrBot 启动入口，不要只重启 Python 进程。
- 普通启动入口会拉起对应 Bot 和 NapCat 子窗口；子窗口确认端口和反连就绪后退出，全部子窗口完成后入口窗口退出。
- NapCat 启动脚本必须同时兼容新版 `napcat\onekey\napcat\launcher-user.bat` 和旧版 `NapCat.*.Shell` / `bootmain` 结构；新版 quick login 使用 `NAPCAT_QUICK_ACCOUNT` 环境变量。
## 更新

- 总更新入口是 `D:\project\qqbot\scripts\update-all.bat`，按顺序调用 NapCat 和 AstrBot 更新实现。
- NapCat 更新由 `tools\runtime-scripts\update-napcat.ps1` 实现；正式更新会先下载并解压新包到临时目录，确认新包准备好后再停止本工作区关联的 NapCat/QQ 进程，把旧 `napcat\onekey` 备份到 `data\napcat\archives\`，替换后迁移账号 OneBot 配置。
- OneBot v11 本身是协议；本仓库实际更新对象是 NapCat 协议端和 AstrBot Core。
- AstrBot 更新由 `tools\runtime-scripts\update-astrbot.ps1` 实现，会先停止本工作区正在运行的 AstrBot uv tool 进程，再默认调用 `uv tool upgrade astrbot --python 3.14`；如果未安装则调用 `uv tool install astrbot --python 3.14`。
- Windows PATH 找不到 `uv` 时，更新脚本可以用 `py -3.14 -m pip install --user -U uv` 自举用户级 uv。
- 更新日志写入 `data\astrbot\logs\updates\`，真实数据仍在 `data\astrbot\data\`。
- 切换到 uv tool 后，修改 `astrbot\` 源码快照不会影响实际运行的 bot2；不要用 `astrbot\` 的源码 diff 判断线上 AstrBot Core 是否已更新。
