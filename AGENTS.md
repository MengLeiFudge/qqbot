# AGENTS.md - QQBot Monorepo 工作流程

本仓库是机器人运行工作区，包含多个应用和共用协议端。

## 基本原则

- 默认使用简体中文沟通。
- 修改前先确认目标子目录：`astrbot/`、`plugins/`、`napcat/`、`scripts/`、`tools/`、`data/`。
- 不把真实 token、QQ 登录态、数据库、运行日志或本机配置提交进 Git。
- 完成可验证改动后需要提交，除非用户明确要求暂不提交。
- 严禁 push，除非用户明确批准。

## 目录边界

- `astrbot/`：AstrBot 官方上游源码 submodule，用于查阅 Core 源码和固定上游版本；不作为 bot2 Core 的日常启动来源，不能放本仓库配置示例或运行态数据。
- `config/astrbot/`：本仓库可提交的 AstrBot 插件、本机配置和人格脱敏示例；由 `tools/maintenance-scripts/export-astrbot-config-examples.py` 从运行态导出。
- AstrBot 行为调整硬限制：配置优先，插件其次，绝不直接修改 AstrBot Core 源码。能通过 `data/astrbot/data/` 运行态配置、AstrBot 参数或插件实现的行为，不允许改 `astrbot/` submodule 或 uv tool 安装目录源码；只有先确认配置和插件都无法实现，并获得用户明确批准后，才允许讨论 Core 补丁。新增、改造或迁移 AstrBot 插件能力前，必须先查 AstrBot 原生配置、WebUI 现有开关、Core 已有行为和本仓库现有插件是否已经提供同类能力；若 AstrBot 原生能力可满足或可复用，应优先复用并只做最小插件补足。若原生能力语义不符合本仓库需求，可以在插件中显式架空或覆盖，但必须在插件配置 schema、README/AGENTS、日志或配置说明里写清楚覆盖了哪个原生设置、默认值、恢复原生行为的方法和冲突风险；禁止无说明地另起一套会和原生设置冲突、重复或绕过原生配置的开关、provider、分段、路由、权限或发送机制。
- `plugins/`：本仓库维护的 AstrBot 本地插件源码；`tools/runtime-scripts/start-astrbot.ps1` 启动前同步到 `data/astrbot/data/plugins/`。新增或迁移 bot2 功能时优先放这里，避免直接修改 `astrbot/` Core 源码或把 `data/` 运行态纳入 Git。
- `astrbot_plugin_qqbot_features` 自己发送的菜单、生图、Lolicon、游戏面板、shapez、Arc 和自动表情图片统一使用插件内随机摘要组件，从固定混合短句池选择 OneBot `data.summary`；不得为摘要额外调用 LLM，也不得修改 AstrBot Core。普通 AstrBot Core 或第三方插件图片保持原发送行为。
- 原 qqbot / NoneBot2 功能已迁入 AstrBot 本地插件；运行时代码不得依赖 `nonebot2/` 源码、`nonebot` 包、NoneBot2 plugin 入口或 OneBot adapter。
- 从旧 qqbot 迁入的纯 Python service 只允许作为 AstrBot 插件内 vendored service 使用，运行态数据根统一为 `data\astrbot\data\plugin_data\qqbot_features_runtime`，迁移配置根统一为 `data\astrbot\data\plugin_data\qqbot_features_config`。插件业务状态和小型结构化配置优先写入 `qqbot_features_runtime\db\qqbot_features.sqlite3`；Lolicon 元数据写入 `qqbot_features_runtime\db\lolicon.sqlite3`；本地 artifact 发布去重状态保留在 `qqbot_features_runtime\fe_artifacts\` 和 `qqbot_features_runtime\local_artifacts\`；菜单图、Arc 猜歌面板、shapez 渲染图和临时面板等可重建生成图只放 AstrBot Core temp 子目录 `data\astrbot\data\temp\qqbot_features\`，由 Core `temp_dir_max_size` 容量清理覆盖；插件可做重复图片副本去重，但不得另起按日期清理策略。不要再新增 `qqbot_features_runtime\data\...` 下的 JSON/TXT 事实源，也不要恢复旧 AI 记忆、公开群上下文快照、TTS、头像或 shapez 静态旧目录。
- AstrBot 账号/身份切换通过启动参数显式控制：日常默认是 `-Target astrbot -FeatureMode full -AstrBotProfile both`，在同一个 AstrBot 管理端内同步两个 `aiocqhttp` 平台，天使默认反连 `6200`，恶魔默认反连 `6201`，并分别拉起两个 NapCat 账号；显式 `-AstrBotProfile demon` 才使用恶魔账号 `2629227874` 单平台，显式 `-AstrBotProfile angel -FeatureMode full -Target astrbot` 才使用天使账号 `1443944862` 单平台。本地插件必须按事件 `self_id` 区分天使/恶魔身份，不能把 `QQBOT_ASTRBOT_PROFILE` 当成双平台模式下的单一身份事实源。AstrBot OneBot 恶魔端口可用 `-AstrBotOneBotPort` 覆盖，天使端口可用 `-AstrBotAngelOneBotPort` 覆盖；不要重新硬编码 `6199`。
- AstrBot provider 选择、模型切换和回退链只归 AstrBot Core / 会话配置 / `provider_settings` 管理，本地插件不得再实现独立 provider 顺序、独立 fallback 或“判定专用模型”配置。`provider_ltm_settings.active_reply.enable` 默认关闭；本地插件不得再 patch `GroupChatContext.need_active_reply`，不得在未显式激活时按定时、消息条数或摘要主动插话。`platform_settings.empty_mention_waiting` 和 `empty_mention_waiting_need_reply` 必须关闭，禁止让 AstrBot Core 的 60 秒空艾特等待抢先处理仅 @；仅 @ 当前 bot、没有正文时由 `astrbot_plugin_topic_concentration` 归一化为无正文显式呼叫，交给当前 provider 按 WebUI 人格生成自然短句。`astrbot_plugin_topic_concentration` 负责显式呼叫、按 `group_id + self_id` 保存的 3 分钟群聊激活状态和双 bot 普通 LLM worker 调度：直接 @、引用当前 bot、明确命名呼叫或拍一拍当前 bot 都是强制激活，当前消息必须由被叫到的 bot 产生可见 LLM 回复；目标已有请求时仍由该目标排队处理，无目标命名呼叫在两只 busy 时也必须按群 balance 选定一只排队。显式模型结果为空或只有控制标记时，携带原 persona、上下文和当前消息，使用同一 provider/model 纠错重试一次；不得切换独立 fallback 或再次执行工具。同时 @ 天使和恶魔时两只分别用自己的身份回答，不得输出“我不能代替姐姐/妹妹回答”类拒答。未明确指定身份但文本包含“棉花糖”时，先判断是否真正在叫机器人；“棉花糖很好吃”这类食物/物件说法必须跳过，“棉花糖，帮我生成一张图片”“棉花糖这个图片是哪个角色”这类请求应按群权重选择一只回复；模糊呼叫判定只允许调用当前会话 provider，失败则不回复。激活窗口内，同群所有真人的普通消息成为当前 bot 主回复模型的候选；模型只返回 `[[QQBOT_SKIP_REPLY]]` 时跳过当前候选且不续期、不改 balance，实际发送可见回复时窗口续到 3 分钟并增加普通回复续期计数，返回可选收尾文本加 `[[QQBOT_DEACTIVATE]]` 时在发送后反激活。每次显式激活必须生成新的状态代际，续期或反激活只能修改本请求捕获的代际，延迟旧响应不得覆盖后来重新激活或反激活的状态。显式激活重置普通续期计数；连续普通续期越多，提示词越必须提高沉默倾向并主动寻找反激活时机。任何群友都能激活或反激活当前群里被叫到的 bot，但不影响其他群、另一只 bot、私聊、固定命令或协议事件。两个内部标记不得发送到 QQ 或写入会话历史。
- `astrbot_plugin_qqbot_features` 的运行态配置入口统一为 `data\astrbot\data\config\astrbot_plugin_qqbot_features_config.json` 和 WebUI “棉花糖功能合集”卡片；不得恢复 `astrbot_plugin_reply_style_guard_config.json`、`astrbot_plugin_source_knowledge_config.json`、`astrbot_plugin_twin_interaction_config.json`、`astrbot_plugin_rightcodes_draw_config.json`、`astrbot_plugin_qqbot_context_bridge_config.json` 或 `meme_manager_config.json` 这类旧独立插件配置兜底。
- AstrBot 好友申请和邀请入群由 `astrbot_plugin_qqbot_features` 处理：默认通过 `auto_approve_friend_requests` 和 `auto_approve_group_invites` 自动同意 OneBot `friend` 请求与 `group/invite` 请求，并记录 action、flag、sub_type 和失败原因；机器人自身入群成功后私聊通知邀请者，文案包含群名和群号，不能在群聊里发送“主人”固定自报；双平台 `both/full` 下天使和恶魔各自按 `self_id` 发送不同的新成员入群欢迎，并各自独立随机选择以“群地位”开头、表达群地位变量减 1 的完整表达式，双子自身入群不触发欢迎；不允许把邀请入群问题交给 LLM 解释成“机器人不能自己加群”。
- RightCodes 生图命令入口归入 `astrbot_plugin_qqbot_features`，不再新增独立固定命令插件；生图积分事实源使用 `data\astrbot\data\plugin_data\qqbot_features_runtime\db\qqbot_features.sqlite3`，旧 `ai\draw_points.json` 仅作为首次导入来源。积分事实源只保留每个 QQ 的当前积分、当前生图模型和最近一次普通群消息带来的缓存昵称，不保留每日免费状态、历史累计消息数或 `message_count` 字段；旧用户和无效模型回退到 `gpt-image-2`。AstrBot 负责普通群消息积分累计；双平台 `both/full` 下只有固定命令 owner 账号累计普通群消息积分，积分和模型选择跨群、跨天使/恶魔共用。`查看积分` 必须返回当前积分、当前模型、该模型单次消耗和模型查看/主切换指令提示，不展示隐藏别名。`积分排行` / `积分排行榜` 返回全局积分前 10，优先只显示缓存昵称；没有缓存昵称时显示保留 QQ 前三位和后三位、中间用星号替代的脱敏 QQ。排行榜不得为补昵称额外调用 OneBot 群成员接口。`切换生图模型 <模型名>` 是主切换指令，`生图模型 <模型名>` 是不进菜单的别名，中文关键字和模型名之间允许有空格或没有空格；模型切换必须走固定命令和双平台 command claim。`棉花糖生图 <提示词>` 只使用已保存模型，不得恢复命令内临时指定模型；生图从第一张开始正常扣分，不得恢复每日免费次数。RightCodes API Key 归 AstrBot 插件配置 `astrbot_plugin_qqbot_features.api_key`，直接在 WebUI/运行态插件配置填写；插件不得再读取 `QQBOT_AI_KEY_RIGHTCODES` 或旧 `.env` 作为生图 key 来源。明确生图命令中的上下文指代提示词可先用当前会话 AstrBot provider 整理为准确生图提示词，再扣积分调用 RightCodes；不得新增独立生图 rewrite provider、独立 fallback 或独立模型顺序。生图提示词整理只能读取当前命令、引用文本和当前/引用消息里的可用图片 URL/路径；只有 `[图片]` 占位、没有可用文字或图片时必须直接提示补充引用或完整提示词，不能让 LLM 猜图。生图成功、失败或超时失败必须引用原始生图请求；失败和超时失败必须退回已扣积分，并提示用户通过模型查看/切换指令重试，不得自动切换模型。
- RightCodes 生图接口知识也归入 `astrbot_plugin_qqbot_features` 的静态 catalog，不新增独立插件；用户问画图接口、请求体、`size`、`1024x1024`、`/v1/images/generations` 或 `/v1/chat/completions` 时，LLM 请求前应注入官方文档摘要。`/v1/images/generations` 明确支持 `size` 字段；`/v1/chat/completions` 适合流式防 Cloudflare 超时，但尺寸控制应写进文本提示。
- 图片理解仍走 AstrBot Core 的 image caption 链路：默认回复 provider 不因图片临时切到 vision provider，避免回复风格漂移。`provider_settings.image_caption_prompt` 必须要求 caption provider 在有人物、动物、动漫/游戏/影视角色或可识别作品线索时，优先返回名称、出处/作品、1-3 个候选、依据和不确定性；无法确定时明确说无法确定并列出可见特征。主回复模型只看到 `<image_caption>`，不直接看原图。
- 公开群上下文 `qqbot_features_runtime\ai\group_context\` 已停止作为运行时事实源；本地插件不得再读取或写入该目录，不得恢复公开群上下文桥接、记录导出、基于 group_context 的引用补文或双子近期公开消息注入。群聊 LLM 上下文使用 AstrBot 当前会话上下文、本轮消息链和可见引用正文；不得读取私聊、token、QQ 登录态、数据库密钥或运行日志作为 LLM prompt 证据。
- 双子 bot 互动由 `astrbot_plugin_qqbot_features` 内部的双子互动模块负责，只在用户明确围绕天使/恶魔/双子关系或另一个 bot 发问时增强当前 bot 的 LLM 上下文或接管明确请求。它必须按事件 `self_id` 注入当前 bot 动态身份事实，用户说“你姐”“你妹”“姐姐”“妹妹”时必须按当前 bot 视角理解，不能让天使把自己当恶魔、恶魔把自己当天使。它不得响应另一个 bot 发出的普通消息，不得冒充另一个 bot 发言、替另一个 bot 认错、解释或承诺修改。用户让被点名 bot 和另一只抱抱、贴贴、道歉、哄人、叫出来或转告这类目标专属双子互动时，必须由被点名目标自己处理；目标忙碌时另一只不得代班完整回答，只能跳过。不得读取私聊、日志、token、QQ 登录态、公开群上下文快照或数据库密钥作为双子互动 prompt 证据。
- AstrBot 源码知识兜底优先用 `astrbot_plugin_qqbot_features` 内部的源码知识模块实现，不改 Core、不依赖 Embedding。可信依据必须优先来自源码、反编译源码、源码邻近 README/设计文档和配置数据，尤其是戴森球计划本体相关源码、相关 mod 源码和 MLJ_DSPmods 辅助模组/工具资料；群聊、群文件、攻略和 release notes 只能作为候选或补充。群号只能作为默认领域偏置，不能当成唯一领域事实；分馏群、星环群也可能问同一 DSP 工作区里的其他模组或工具，精确模组名、工具名、目录名和机制词应优先触发跨默认群域检索。源码检索模块只读明确配置的源码根，必须跳过 `.git`、`.codex`、`bin`、`obj`、`.vs`、`.idea`、`packages`、`node_modules`、`logs`、缓存和密钥类文件；不得读取私聊、token、QQ 登录态、数据库密钥、运行日志或本仓库运行态 `data`。源码知识默认按低成本注入，复杂技术追查需要大文件或更多证据时，再在运行态配置里临时调高 `source_knowledge_max_results`、`source_knowledge_max_chars`、`source_knowledge_max_files_per_domain` 和 `source_knowledge_max_file_bytes`。
- 双平台共用 `astrbot_plugin_qqbot_features` 内部表情管理模块的本地表情包索引，运行态事实源兼容保留在 `data\astrbot\data\plugin_data\meme_manager\meme_index.json` 和 `memes\`，模块源码事实源是 `plugins\astrbot_plugin_qqbot_features\meme_manager\`；不再保留独立 `plugins\meme_manager\` 插件，启动前也不再同步独立 `meme_manager` 到 `data\astrbot\data\plugins\meme_manager\`，启动脚本应清理旧运行态插件目录。固定指令统一按本地插件模式管理：群聊和私聊都能触发；群聊可以 @ 当前 bot 后发送，也可以不 @ 直接发送；每个指令只有一个主指令，菜单仅显示主指令；别名只作为近似含义触发，不在菜单显示；指令不以 `/` 等特殊符号开头，直接使用中文或英文字母。旧 `mlj_pack` 不再保留在仓库 `data/` 顶层；历史导入只能由 `tools\maintenance-scripts\migrate-meme-pack-to-manager.py <外部index.json路径>`、兼容命令 `tools\maintenance-scripts\sync-meme-pack.py <外部index.json路径>` 或后台接口手动指定外部来源。轻松日常、玩梗、吐槽、撒娇和短情绪回复应优先使用表情，短情绪闲聊允许纯表情回复，`auto_send_enabled=false` 的敏感支付、涩涩慎用、待复核类别不得自动发送。表情管理通过 `表情管理 开启管理后台` 提供本地图库 UI，支持预览、搜索、分类移动、类别编辑、单图说明/关键词/适用场景/禁用场景和自动发送开关；发送链路不额外调用 LLM 做单图选择，只让主 LLM 决定是否用表情和粗类别，再由插件本地 selector 按类别、关键词、禁用场景、权重和近期去重选图；LLM 输出的 `&&标签&&` 和可识别的半截/畸形表情标签必须在发送前清理，不能把裸标签文本发到群聊。
- 本地 artifact 发布迁移到 `astrbot_plugin_local_artifact_api`，在 AstrBot `full` 模式下监听 `127.0.0.1:8080` 的兼容 `POST /admin/api/artifacts/publish-local`；它使用插件内发布服务和 `data\astrbot\data\plugin_data\qqbot_features_runtime` 发布状态，通过 AstrBot aiocqhttp OneBot 上传群文件，不改 AstrBot Core。发布服务必须独立打开 zip 计算内容 hash，与自身缓存比对后再决定是否删除、上传和发群消息；客户端传入的 `content_sha256` 只能用于一致性校验，不能作为唯一判重事实源。AstrBot-only 启动会清理旧 8080 占用并接管该端口。
- AstrBot `full` 模式启动验证必须同时覆盖 WebUI `6185`、OneBot `6200/6201` 和 artifact API `8080`；`LocalArtifactApi failed to listen`、`WinError 10013` 或 `PermissionError` 不能被当成 ready 状态忽略。
- 双平台运行时，另一个 bot 的普通输出不得触发当前 bot 回复；普通 LLM 请求只来自明确 @、引用当前 bot、私聊、命名呼叫、拍一拍当前 bot或当前群当前 bot 激活窗口内的普通候选。点名谁就谁处理：只 @、引用或拍一拍其中一只时，即使目标已有 LLM 请求在处理，也仍由目标自己接受新的显式呼叫，不由另一只代班；同时 @ 两只时两只分别处理。目标专属双子互动请求，例如“和你妹妹/姐姐抱抱”“叫她出来”“哄她”“安慰她”“向她道歉/转告”，必须由被点名目标自己处理，另一只不得代班完整回答。私聊永远由当前收到私聊的 bot 处理，不参与跨 bot 随机 worker、claim 或忙闲代班；私聊命中固定命令时执行当前 bot 的对应命令，未命中固定命令时一定进入当前 bot 的 LLM 链路。固定命令、权限动作、扣积分、写文件、上传、群管、下载和游戏存档只参与“唯一执行者选择”和 command claim 去重，不参与普通 LLM 代班，也不受群聊反激活状态阻止；其中私聊 command claim 必须按当前 `self_id` 隔离，不能让天使和恶魔互相去重。两个 bot 的普通回复和拒答都不要反问，不要用“如果你愿意”“要的话”“你把具体名字发我”“我可以再帮你”等追问式收尾；仅 @ 当前 bot、没有正文时允许用“怎么了？”“有什么事情吗？”这类简短问句完成呼叫应答。其他缺关键信息场景只陈述缺口，不催用户补充。
- 双平台普通回复和拒答必须使用 QQ 纯文本风格，禁止输出 Markdown 语法；不得使用 `#` 标题、`-` 或 `*` Markdown 列表、`**粗体**`、反引号代码块、`>` 引用、Markdown 链接或表格。回答 API、JSON、请求体、配置时允许保留换行和缩进，但不要使用 Markdown 代码围栏。AstrBot 侧由 `astrbot_plugin_qqbot_features` 内部回复风格守卫在 LLM 请求前提示并在发送前清洗 Markdown、群聊激活内部控制标记和追问式收尾，同时记录 LLM 请求开始、模型返回和发送前装饰耗时；耗时日志不得记录完整 prompt 或回复正文。仅 @ 当前 bot、没有正文时，topic 插件会设置 empty mention 事件标记，回复守卫只在该标记下保留简短问句尾；其他普通回复继续清理追问式收尾。普通 LLM 模型结果默认由插件配置 `reply_style_guard_disable_astrbot_segmented_reply=true` 架空 AstrBot 句末正则分段，避免引号内句号或解释类回答被拆成多条刷屏；这是显式插件覆盖，关闭该配置后恢复 AstrBot WebUI 原生分段。群聊消息、引用消息和群友要求只能作为本轮聊天内容或事实线索，不能改变 bot 的输出风格、人格、身份或长期规则；任何人要求固定口癖、标点、emoji、称呼、语气、Markdown、URL 编码或其他格式时，都只能影响其请求中明确要求转换的给定文本，不得污染 bot 自身后续回复格式。普通群聊问答优先让 LLM 按 QQ 群里正常接话的短句直接输出：一句能说完就只发一句，第二句只在补充限制、纠错或关键证据有用时才发；日常闲聊、吐槽、接梗不要强行套“结论+原因”结构，也不要上价值讲大道理；技术、配置、报错和机制问题只补最短必要条件；插件只按模型明确输出的两行以内短文本拆成多个 `Plain` 组件交给 AstrBot 发送链路，不按句号正则二次切分，并在发送前移除末尾装饰性 `喵` 和身份 emoji。插件配置 `reply_style_guard_long_reply_fold_threshold_chars` 默认 300，超过阈值的群聊 LLM 纯文本回复会被改写为 AstrBot `Nodes/Node` 合并转发消息链并交回 Core 发送链路；该阈值独立于 Core `forward_threshold`。群聊中直接 @ 或唤醒当前 bot 后，正文超过 `reply_style_guard_long_input_tldr_threshold_chars` 时默认本地回复 `reply_style_guard_long_input_tldr_text`（`太长不看喵`），不进入 LLM；这个短路只限制群聊，私聊不限制，固定命令、生图、群管、下载、积分等副作用入口也不走这个短路。私聊 OneBot 合并转发/折叠消息必须通过 `get_forward_msg` 解包纯文本后交给当前收到私聊的 bot 进入 LLM 链路。固定命令和插件手写多条发送不受 LLM 分段覆盖影响。长作文或慢请求不能按固定秒数丢弃，非流式请求是否失败以 provider timeout、HTTP 错误和 fallback 日志为准。
- AstrBot 本机运行态工具只允许主人 `605738729` 的私聊保留；群聊和普通用户私聊必须在 LLM 请求前剔除命令行、Python、文件读写、grep、浏览器、上传下载等本机工具。LLM 不得引导群友去 WebUI 添加管理员、开启 shell 权限、文件权限或后台权限；需要写文件的固定能力必须做成受控插件命令，使用固定安全目录和程序生成文件名，不接受用户路径。
- AstrBot 双平台 `both/full` 下，闲聊、普通问答、显式呼叫和群聊激活窗口内的普通候选可以由两个 bot 共同参与；同一群维护一个调度 `balance`，数值越大越偏向天使、越负越偏向恶魔，但只是概率偏置，不能变成必然选择。未明确指定身份的命名呼叫按群权重选一个 worker；激活候选按当前 `self_id` 分开 claim，因此两只 bot 都已激活时可各自判断同一条普通消息是否值得回复。同时 @ 双方的固定命令只选一个执行者，另一只最多发短状态评论；同时 @ 双方的普通聊天允许两只各自用自己的身份回答，并注入“用户同时叫了两个人”的上下文；用户同时对两只表达喜欢、感谢、夸奖、吐槽、摸头或贴贴时，每只只能代表当前 bot 独立回应，不能替另一个 bot 接受、感谢、道歉、承诺或猜测对方心情。群聊固定命令必须按目标 @、按群权重和 canonical claim 唯一执行；claim key 优先使用群号、发送者、当前纯文本、@ 目标、引用消息和时间桶，不依赖双平台可能不一致的 message_id；引用消息优先使用引用正文摘要，只有没有引用正文时才退回平台 reply_id，避免同一条引用消息在天使/恶魔两路产生不同 claim。私聊固定命令按当前 `self_id` 独立执行，不和另一只 bot 共享去重 claim。菜单、帮助、指令、生图、下载、群文件清理等固定命令不得因双平台群聊重复执行。AI 或普通 LLM 判定“像固定功能”的自然语言请求只能提示真实指令和消耗/副作用，不能直接执行扣积分、写文件、上传、群管、下载或改存档。
- 普通聊天文本不得在 AstrBot 本地插件里按“低信息、在吗、111、真的吗、回复慢、测试、探活”等启发式直接生成本地回复；只要命中明确 @、引用当前 bot、私聊、命名呼叫、拍一拍当前 bot或激活窗口内的普通候选，且没有命中明确命令、游戏会话答案、协议事件处理或本地硬安全提醒，就必须交给当前 LLM 链路处理。未激活且未呼叫的普通群聊保持静默；激活候选是否发言由主模型的正文、`[[QQBOT_SKIP_REPLY]]` 或 `[[QQBOT_DEACTIVATE]]` 决定。插件可以做 prompt 注入、记忆检索、输出清洗和路由门控，但不能凭空补一句固定兜底文本。
- 双平台所有群聊和私聊 LLM 回复都不做危机处理；自述、倒霉、考试迟到、没吃饭、没睡觉等默认按玩笑、夸张、钓机器人或时间梗分析。分析不出发言原因时不回答，不编原因，不输出危机干预、急救、报警、健康建议或严肃安慰；凭据泄露等本地硬安全提醒仍按既有规则执行。
- 双平台不保留“严肃模式”人格切换；所有群聊都按轻松水群氛围处理。技术、代码、报错、配置、群管理和安全提醒也必须保持当前天使/恶魔人设语气，但结论要准确、可执行，不能用卖萌或吐槽遮住关键信息。复读、频繁艾特、怪图/表情包和深夜修仙默认是水群行为，直接被叫到时短句接梗、安慰或吐槽；未显式激活时不得恢复普通主动接话，激活窗口内也必须由主模型主动克制并在连续续期后优先寻找静默时机。恶魔棉花糖平时不主动使用固定“喵”口癖，不要写“哼...喵”这类模板化短口癖。AstrBot 侧天使/恶魔身份、人设、说话风格和双子关系只来自 AstrBot WebUI 人格配置（运行态 `data\astrbot\data\data_v4.db`）；本地插件不得内嵌或覆盖固定人格、水群风格或固定口癖，只能注入动态事实、接口资料、权限边界和 QQ 纯文本/短气泡这类格式边界。
- `napcat/`：共用 NapCat 程序包；当前账号 OneBot 配置随一键包放置并由更新脚本迁移。启动和更新脚本必须确保官方内置插件 `napcat-plugin-builtin` 存在于 `napcat\onekey\napcat\plugins\`，让 `#napcat` 这类 NapCat 框架固定指令在 NapCat 层优先匹配，不得在 AstrBot 插件里模拟该命令。`data\napcat\downloads\` 和 `data\napcat\archives\` 只作为更新事务临时目录，成功更新后必须清理下载包、解压目录和旧包备份；若更新中途失败且旧 `onekey` 已被移走，临时旧包备份可保留为人工恢复点。
- `data/`：统一运行态根目录，默认忽略，不进 Git；顶层只保留 `data\astrbot\` 和 `data\napcat\`，旧迁移源、旧启动标记、旧下载包、旧归档、临时目录和重复配置不得作为日常运行态保留。
- `data\astrbot\data\dist\`、`dashboard.zip` 和 `plugins.json` 是 AstrBot Core WebUI / 插件市场缓存，不是本仓库插件事实源，也不作为服务器迁移必要数据；dashboard 更新后若 `dist` 残留旧 hash 资源，应按 `dashboard.zip` 清单移动到项目根 `.codex\trash\`。
- `scripts/`：只保留 `start-all.bat` 和 `update-all.bat` 两个根级 Windows 用户入口。
- `tools/runtime-scripts/`：`scripts/` 两个 all 入口调用的内部 PowerShell 启动、重启和更新实现。
- `tools/maintenance-scripts/`：配置示例导出、表情迁移等非日常维护脚本。

## 配置示例导出

- AstrBot 可提交配置示例放在 `config/astrbot/`；当前运行态配置导出入口是 `python3 tools/maintenance-scripts/export-astrbot-config-examples.py`。
- 导出脚本可读取 `data\astrbot\data\cmd_config.json`、`data\astrbot\data\config\*.json` 和 `data\astrbot\data\data_v4.db` 的 personas 表；输出前必须剔除 LLM provider/model/provider_sources/provider_settings/fallback/image-caption/embedding 路由，并脱敏 key、token、secret、password、cookie、authorization、custom headers/body 等字段。
- example 可以保留非密钥运行形态，例如端口、bot 账号、群号、插件开关、功能模式和人格文本；不得提交真实 provider key、OneBot token、登录态、数据库密钥、运行日志或会话历史。

## 数据路径

- AstrBot 启动时应设置：
  - `ASTRBOT_ROOT=D:\project\qqbot\data\astrbot`
  - AstrBot 实际数据目录为 `D:\project\qqbot\data\astrbot\data`
  - 迁移功能运行态数据为 `D:\project\qqbot\data\astrbot\data\plugin_data\qqbot_features_runtime`
  - 迁移功能配置为 `D:\project\qqbot\data\astrbot\data\plugin_data\qqbot_features_config`
  - Core 由 `uv tool` 管理，启动脚本优先调用已安装的 `astrbot.exe run -p 6185` 或 PATH `astrbot run -p 6185`；日常启动不自动 `uv tool run --from astrbot` 联网拉包，未安装时先运行 `scripts\update-all.bat`。

## Linux / 1Panel 部署与同步

- Linux / 1Panel 服务器只作为 AstrBot + 双 NapCat 的运行端；本机仓库是长期开发事实源。
- 1Panel 官方安装只覆盖 AstrBot Core，不自动包含本仓库双棉花糖插件、两路 aiocqhttp 平台、两个 NapCat 协议端和 `plugin_data` 运行态；完整步骤维护在 `docs/server-deployment-linux.md`。
- 后续修改默认走：本机改动 -> 本机验证 -> Git 提交 -> 服务器 `git pull` -> 同步 `plugins/` 到 AstrBot 数据目录 -> 重启 AstrBot / NapCat。不要把服务器直接 Codex 改动作为长期主线。
- 服务器直接编辑只允许紧急热修；热修后必须把服务器 diff 拉回本机复核、提交，并让服务器回到 Git 跟踪版本。不得提交服务器上的 token、QQ 登录态、数据库、运行日志或私聊数据。

## 验证

- 结构变更后至少检查：
  - `git status --short`
  - 根目录是否只有一个 `.git`
  - `data/` 是否未进入 Git
- 根目录 `tests/` 保留 AstrBot 本地插件、启动脚本和配置导出回归测试；相关改动优先运行 `py -3.14 -m pytest tests` 或本机可用的等价 Python 命令。
- AstrBot Core submodule 不作为运行态；Core 相关验证优先使用 ruff、`python -m py_compile` 和实际 uv tool 启动探针。
- AstrBot Core 运行/更新脚本变更优先做 PowerShell 语法检查；不要把 submodule 源码测试结果当作 uv tool 运行态验证。
- 修改 AstrBot persona、插件注入提示词、回复风格守卫、LLM 路由提示、显式呼叫/群聊激活判定提示、源码知识、图片 caption prompt 或接口资料注入等会影响模型输出的 prompt 后，必须使用实际运行配置对应的 AI/provider 接口做真实模拟调用，样例至少覆盖本次变更目标场景；验证记录必须包含关键输入、实际模型输出、provider/model 和判断结论。允许直接调用对应 AI 接口完成验证，不能只靠想象、静态阅读或未调用模型就声称回答符合预期。
- 对本仓库启动、重启、更新、进程残留、端口占用、脚本编排和机器人运行态修复，完成脚本或配置改动后必须直接执行真实入口验证；不要因为会停止现有机器人、关闭 NapCat/QQ、替换 `napcat\onekey`、升级 uv tool、重启 AstrBot、清理残留进程或短暂中断服务而停下来要求用户再次确认。用户提出这类问题本身即表示要解决到真实运行可用。

## 启动与重启

- 日常启动入口是 `D:\project\qqbot\scripts\start-all.bat`，默认启动 AstrBot 天使+恶魔双平台。
- 修改会影响正在运行机器人的代码、配置、提示词、运行包或启动脚本后，必须强制重启对应机器人并做启动验证；不能只停在“已修改/已提交”，也不能只运行会复用现有进程的默认 ensure-running 入口。若当前环境无法重启，最终回复必须明确写出未重启、原因和应执行的入口。
- 只影响 AstrBot Core、`data\astrbot\data\cmd_config.json`、AstrBot persona 或 uv tool 运行包的改动，重启 bot2：`tools\runtime-scripts\start-all.ps1 -Target astrbot -SkipInstall -AstrBotProfile both -FeatureMode full -ForceRestart`；日常 `scripts\start-all.bat` 默认是 ensure-running，现有 `6185`、`6200/6201`、`8080` 和两路 NapCat 连接都 ready 时会直接复用当前进程。
- AstrBot 接管已迁移自动事件时，日常启动使用 `scripts\start-all.bat`；修改后验证或需要重新加载插件/配置时使用显式 `tools\runtime-scripts\start-all.ps1 -Target astrbot -SkipInstall -AstrBotProfile both -FeatureMode full -ForceRestart`。如本机端口冲突，可加 `-AstrBotOneBotPort <端口>` 和 `-AstrBotAngelOneBotPort <端口>` 同步 AstrBot 和 NapCat 反连配置。
- 需要 NapCat 重新反连时也使用普通 AstrBot 启动入口，不要只重启 Python 进程。
- 普通启动入口默认只保留一个入口终端，按固定前缀输出组件摘要，例如 `[Launcher]`、`[AstrBot]`、`[NapCat] [Angel]`、`[NapCat] [Demon]`；需要恢复旧多子窗口观察方式时显式使用 `-UseChildWindows`。默认启动是 ensure-running：先探测现有 AstrBot WebUI `6185`、OneBot `6200/6201`、artifact API `8080` 和两路 NapCat established 连接，全部 ready 时直接复用，不杀进程；缺失组件或显式 `-ForceRestart` 时才启动/重启。冷启动和强制重启时，启动器必须等 AstrBot WebUI `6185`、OneBot `6200/6201` 和 artifact API `8080` 全部 ready 后，才启动对应 NapCat 账号，避免 NapCat 日志把 AstrBot 启动耗时混成自身等待耗时；`start-astrbot.ps1` 应在 stdout 输出 `AstrBot startup phase: ...` 预启动阶段日志，`start-all.ps1` 等待摘要应识别 Core、插件、provider、KnowledgeBase 和 WebUI 等阶段。启动器临时控制标记写入 `data\astrbot\logs\start_all\<runId>\control\`，不得再写入顶层 `data\launcher\`。双平台 `both/full` 下两个 NapCat 账号不得无条件并行启动，必须通过 `data\napcat\quick-login\<account>.ready` 判断是否可快速登录：任一账号缺少标记或上次失败时按天使优先串行启动，避免两个账号同时写共享 `napcat\onekey\napcat\cache\qrcode.png` 导致控制台二维码不可用时扫错账号；两个账号标记都存在时允许按天使优先并行启动以缩短重启时间；某账号未成功反连时必须清除该账号标记。启动器控制台诊断和 bat 失败停窗文案保持英文/ASCII，避免 Windows 控制台无法显示 NapCat 中文日志或本地化 `pause` 提示时出现乱码；完整原始日志保留在 `data\astrbot\logs\start_all\<runId>\`。
- NapCat 启动脚本必须同时兼容新版 `napcat\onekey\napcat\launcher-user.bat` 和旧版 `NapCat.*.Shell` / `bootmain` 结构；新版 quick login 使用 `NAPCAT_QUICK_ACCOUNT` 环境变量。启动 NapCat 账号前必须先运行 `tools\runtime-scripts\ensure-napcat-builtin-plugin.ps1` 校验或恢复官方 `napcat-plugin-builtin`，避免 `#napcat` 被透传到 AstrBot/LLM。
## 更新

- 总更新入口是 `D:\project\qqbot\scripts\update-all.bat`，按顺序调用 NapCat 和 AstrBot 更新实现。
- 更新入口默认交互式：NapCat 下载前提示当前版本、目标 release、asset、下载 URL、zip 路径和后续替换动作；AstrBot install/upgrade 前提示当前 tool 状态、计划 uv 命令和会处理的运行进程。用户拒绝某组件时该组件跳过并退出 0；无人值守才显式传 `-AssumeYes` 自动确认。
- NapCat 更新由 `tools\runtime-scripts\update-napcat.ps1` 实现；会先查询 GitHub 最新 release，本地已是最新 release 时直接跳过下载和替换，并清理旧更新缓存。本地版本优先读 `napcat\onekey\.qqbot-napcat-release.json`，旧包无标记时回看最近成功的 NapCat 更新日志；需要更新时，确认后才下载并解压新包到临时目录，确认新包准备好后再停止本工作区关联的 NapCat/QQ 进程，临时移走旧 `napcat\onekey`，替换后迁移账号 OneBot 配置，并校验或恢复官方 `napcat-plugin-builtin`，成功后删除本次下载包、解压目录和旧包临时备份。
- OneBot v11 本身是协议；本仓库实际更新对象是 NapCat 协议端和 AstrBot Core。
- AstrBot 更新由 `tools\runtime-scripts\update-astrbot.ps1` 实现；用户确认后会停止本工作区正在运行的 AstrBot uv tool 进程，再默认调用 `uv tool upgrade astrbot --python 3.14`；如果未安装则调用 `uv tool install astrbot --python 3.14`。
- Windows PATH 找不到 `uv` 时，更新脚本可以用 `py -3.14 -m pip install --user -U uv` 自举用户级 uv。
- 更新日志写入 `data\astrbot\logs\updates\`，真实数据仍在 `data\astrbot\data\`。
- 切换到 uv tool 后，修改或切换 `astrbot\` submodule 不会影响实际运行的 bot2；不要用 `astrbot\` 的源码 diff 判断线上 AstrBot Core 是否已更新。需要更新源码参考时，更新 submodule 指针并提交外层 gitlink；需要更新实际运行 Core 时走 `scripts\update-all.bat`。
