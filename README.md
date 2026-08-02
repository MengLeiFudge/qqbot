# QQBot Workspace

这是本机机器人 monorepo 工作区，按运行组件拆分：

```text
qqbot/
├── astrbot/       # AstrBot 官方源码 submodule，只作参考；实际 Core 由 uv tool 管理
├── plugins/       # 本仓库维护的 AstrBot 本地插件源码，启动前同步到运行态
├── config/        # 可提交的脱敏配置示例
├── scripts/       # Windows 用户入口，只保留 start-all.bat / update-all.bat
├── tools/         # 启动、更新和维护脚本实现
├── tests/         # 本仓库启动脚本、插件和配置导出回归测试
├── data/          # 统一运行态根目录，默认不进 Git
└── napcat/        # 共用 NapCat / QQ 登录端程序包，默认不进 Git
```

## 数据目录

`data/` 存放真实配置、数据库、日志、QQ 登录态、AI 会话、插件数据和更新状态。顶层只保留两类运行态：

- `data/astrbot/`：AstrBot root；Core 会在其下维护 `data/`、`logs/` 和 `.astrbot/`。
- `data/napcat/`：NapCat 更新状态、登录辅助标记和运行日志；历史下载包、旧包备份和旧启动标记不作为日常运行态保留。

- `data/astrbot/data/`：AstrBot 的 `cmd_config.json`、`data_v4.db`、插件和插件数据。
- `data/astrbot/data/plugin_data/qqbot_features_runtime/`：从旧 qqbot 迁入的轻量运行态。插件业务状态优先存放在 `db/qqbot_features.sqlite3` 和 `db/lolicon.sqlite3`；本地 artifact 发布去重状态保留在 `fe_artifacts/` 和 `local_artifacts/`；不再保留旧 AI 记忆、公开群上下文快照、TTS、头像和 shapez 静态旧目录。
- `data/astrbot/data/temp/qqbot_features/`：本地插件的菜单图、Arc 猜歌面板、shapez 渲染图和临时面板等可重建生成图。该目录进入 AstrBot Core `temp_dir_max_size` 容量清理范围；插件只额外删除超过安全窗口的重复图片副本，不做独立按日期清理。
- `data/astrbot/data/plugin_data/qqbot_features_config/`：从旧 qqbot 迁入的 `.env` 和 `qqbot.toml`，供 AstrBot 本地插件读取必要本机配置。
- `data/astrbot/data/plugin_data/meme_manager/`：`astrbot_plugin_qqbot_features` 内部表情管理模块的运行态事实源，包含 `memes/` 图片目录、`meme_index.json` 单图语义索引和兼容的 `memes_data.json` 类别描述。
- `data/astrbot/data/dist/`、`data/astrbot/data/dashboard.zip` 和 `data/astrbot/data/plugins.json` 属于 AstrBot Core WebUI / 插件市场缓存，不作为服务器迁移事实源；dashboard 更新后留下的旧 hash 资源应按 `dashboard.zip` 清单清理。
- `data/napcat/quick-login/`：双账号 NapCat 快速登录标记。

可提交配置模板只放在：

- `config/astrbot/`：AstrBot 插件、本机配置和人格示例；可用 `python3 tools/maintenance-scripts/export-astrbot-config-examples.py` 从当前运行态重新导出，脚本会剔除 LLM provider/model 路由并脱敏 key/token/secret。

不要再使用旧 NoneBot2 配置入口；AstrBot 本地迁移插件读取 `data/astrbot/data/plugin_data/qqbot_features_config/`。

AstrBot Core 不从 `astrbot/` submodule 启动；`tools/runtime-scripts/start-astrbot.ps1` 会优先直调 `uv tool` 安装出的 `astrbot.exe`，再回退到 PATH 中的 `astrbot`，并通过 `ASTRBOT_ROOT=D:\project\qqbot\data\astrbot` 读取真实数据。日常启动不会自动使用 `uv tool run --from astrbot` 联网拉包；如果 AstrBot tool 尚未安装，先运行 `scripts\update-all.bat`。

首次克隆或换机器后，用 `git submodule update --init --recursive` 拉取 `astrbot/` 官方源码。需要刷新上游源码参考时，更新 submodule 指针并提交外层 gitlink；实际运行包仍通过 `scripts\update-all.bat` 更新 uv tool。

`plugins/` 下的本地插件会在 `tools/runtime-scripts/start-astrbot.ps1` 启动前复制到 `data\astrbot\data\plugins\`。当前 `astrbot_plugin_qqbot_features` 负责 AstrBot 的本地功能入口：功能清单、图片菜单、Factorio 下载链接、Sub2API 账号用量查询、复读、入群欢迎、本地表情包管理、按配置自动同意好友申请和邀请入群、群文件清理通知、shapez 短代码渲染、Arc PTT 推荐、活动梯子查询、字母猜歌、曲绘猜歌、作者限定安装包下载、养鲲、落樱之都基础玩法、Lolicon 基础取图和 Lolicon 群配置、RightCodes 生图和生图积分；旧 AI runtime 使用 AstrBot 原生链路替代。拍一拍不在功能合集里生成固定或随机回复；仅 @ 当前 bot 和拍一拍当前 bot 都由对话调度插件视为一次显式呼叫。

功能合集发送菜单、生图、Lolicon、游戏面板、shapez、Arc 和自动表情等图片时，会从本地 32 条混合短句池随机选择一条写入 OneBot 图片 `summary`。这条摘要用于 QQ 会话列表等外层图片预览，不作为额外文本发送，也不额外调用 LLM；AstrBot Core 和第三方插件自行发送的图片不受影响。

`astrbot_plugin_local_artifact_api` 负责 AstrBot 的本地构建产物发布兼容入口。AstrBot `full` 模式下会在 `127.0.0.1:8080` 提供 `POST /admin/api/artifacts/publish-local`，保持原 NoneBot2 localhost-only 请求体、Git 上下文校验和 OneBot 群文件上传行为，供 `AfterBuildEvent.exe 1` 这类本机白名单构建流程继续发布 zip 产物。服务端会独立读取 zip 内容计算内容 hash，并和自己的发布缓存比对；内容未变化时不删除旧文件、不上传、不发群消息。
`tools\runtime-scripts\start-all.ps1` 日常默认等价于 `-Target astrbot -FeatureMode full -AstrBotProfile both`。默认模式是 ensure-running：如果现有 AstrBot WebUI `6185`、OneBot `6200/6201`、artifact API `8080` 和两路 NapCat 反连已经 ready，会直接复用当前运行态，避免无意义冷重启；如果端口或连接缺失，才启动缺失组件。需要强制应用插件、配置、脚本或 uv tool 运行包变更时，给 PowerShell 入口加 `-ForceRestart`，此时会清理旧端口和旧进程并重新等待 `6185`、`6200/6201` 和 `8080` 全部就绪；如果 artifact API 绑定失败，启动入口会失败而不是只报告 AstrBot WebUI ready。

RightCodes 生图命令已归入 `astrbot_plugin_qqbot_features`。生图积分事实源使用 `data\astrbot\data\plugin_data\qqbot_features_runtime\db\qqbot_features.sqlite3`；旧 `ai\draw_points.json` 首次读取时会自动导入，之后不再作为写入事实源。每个 QQ 跨群、跨天使/恶魔共用当前积分和当前生图模型；旧用户默认使用 `gpt-image-2`。每条群消息都会把群名片、QQ 昵称和更新时间缓存到插件 SQLite：显示当前群成员时优先该群群名片、其次该群 QQ 昵称；当前群没有记录时只回退其他群最新的 QQ 昵称，不使用其他群群名片；仍没有才回退 QQ。`积分排行` / `积分排行榜` 返回全群累计积分最高的 10 个用户，并在最终回退 QQ 时做中间位星号脱敏。`查看积分` / `balance` / `points` 返回当前积分、当前模型和单次消耗。`生图模型` 查看模型，`切换生图模型 <模型名>` 持久切换，`生图模型 <模型名>` 是不进菜单的别名；中文指令关键字和模型名之间允许有空格或没有空格。`棉花糖生图 <提示词>` 只使用已保存模型，不再支持命令内临时指定模型。RightCodes API Key 直接填写在 AstrBot 插件配置 `astrbot_plugin_qqbot_features.api_key`，不再读取 `QQBOT_AI_KEY_RIGHTCODES` 或旧 `.env`。明确生图命令里的上下文指代提示词可先用当前会话 AstrBot provider 整理，再扣积分调用 RightCodes；拿不到可用引用图片或上下文时不扣积分。生图成功、失败或超时失败都会引用原始请求；默认 240 秒总超时，失败会退回本次扣除的积分并提示模型查看和切换指令。

当前 `point_multiplier=1000` 时，模型单次消耗为：`gpt-image-2` 40 积分（$0.04）、`gpt-image-2-vip` 130 积分（$0.13）、`nano-banana` 140 积分（$0.14）、`nano-banana-2` 120 积分（$0.12）、`nano-banana-2-lite` 50 积分（$0.05）、`nano-banana-pro` 180 积分（$0.18）。生图从第一张开始正常扣分，不再提供每日免费次数。

RightCodes 生图接口问答也归入 `astrbot_plugin_qqbot_features` 的静态知识 catalog。用户问 RightCodes 画图接口、请求体、`size`、`1024x1024`、`/v1/images/generations` 或 `/v1/chat/completions` 时，插件会在 LLM 请求前注入官方文档摘要：`/v1/images/generations` 支持 `size` 字段，`/v1/chat/completions` 适合流式防超时。

图片理解仍使用 AstrBot Core 的 image caption 链路，不把默认回复模型临时切到 vision provider，避免回复风格漂移。当前 caption prompt 要求识图模型在有人物、动物、动漫/游戏/影视角色或作品线索时，优先返回名称、出处/作品、候选、依据和不确定性；主回复模型只读取这段 `<image_caption>`，不直接看原图。

Sub2API 用量查询归入 `astrbot_plugin_qqbot_features` 固定命令：群里发送 `用量` 会返回一张图片，按账号依次展示 5h / 7d 额度卡和该账号自己的当前 7d 周期用户消费榜，所有账号区块结束后再展示全账号当日 / 本周 / 30 天消费榜。每个账号榜的窗口起点为该账号原始 `seven_day.resets_at - 7 days` 后向下取整到所在小时（例如 09:10 从 09:00 桶开始），按稳定 `account_id` 过滤：起点当天从该小时桶开始汇总小时趋势，后续日期按自然日汇总 `actual_cost`；不同账号不再合计，每个榜显示该账号全部非零用户并按金额降序。账号和用户都由插件自动分页发现，账号改名、增加或删除后不需要改配置；用户显示名优先使用 username，为空时展示等长脱敏邮箱，底部三个周期消费全部为 0 的用户不进入全账号榜。底部消费按 `Asia/Shanghai` 统计并使用 Sub2API `actual_cost`：当日从最近已到达的 08:00 开始（08:00 前回退到前一天），本周从最近已到达的周一 08:00 开始（周一 08:00 前回退到上周一），30 天为当日起点往前 30 个日历日并包含当前小时桶；三个周期以同一次后台刷新时刻为结束时刻。插件启动后按 `sub2api_refresh_interval_seconds` 后台定时刷新：底部用户榜和账号主动刷新各自每 300 秒一次、相隔半个周期，各账号 7d 周期榜跟随账号刷新并共享本轮结束时刻；群消息只读取最近一次缓存，不发起 Sub2API 请求。账号列表或底部用户榜刷新失败时保留上次成功缓存；单个账号周期榜失败时只保留该账号自己的上次成功榜并在对应区块显示错误，不阻止其他账号更新。Sub2API 当前用户消费接口单次最多返回 200 人；超过时会明确报错，不会把未返回用户的消费误报为零。`sub2api_alert_group_ids` 可填写英文逗号分隔的 QQ 群号，任一账号 5h 用量首次跨过 80%、90%、95% 时自动提醒这些群；回落到阈值以下后才允许再次触发同一阈值。Sub2API 根地址和 Admin API Key 填在 AstrBot 插件运行态配置 `sub2api_base_url`、`sub2api_admin_api_key`，真实 key 不写入源码或示例配置。

`astrbot_plugin_qqbot_features` 默认按 `full` 模式运行，由 AstrBot 接管已迁移自动事件。旧 `dual` 配置仅作为兼容值保留，运行时也按 `full` 处理。日常使用 `scripts\start-all.bat` 启动同一 AstrBot 管理端内的天使+恶魔双平台。

AstrBot 启动入口支持显式选择 bot 身份：日常默认是 `both/full`，在同一个 AstrBot 管理端里同步两个 `aiocqhttp` 平台，天使默认反连 `ws://127.0.0.1:6200/ws`，恶魔默认反连 `ws://127.0.0.1:6201/ws`；只有显式 `-AstrBotProfile demon` 才使用恶魔棉花糖账号 `2629227874` 单平台，显式 `-AstrBotProfile angel -FeatureMode full` 才使用天使账号 `1443944862` 单平台。`scripts\start-all.bat` 和直接运行 `tools\runtime-scripts\start-all.ps1` 默认都是 `both/full`。本地插件会按每条消息的 `self_id` 区分天使或恶魔身份。

`tools\runtime-scripts\start-all.ps1` 默认在单个入口终端中显示启动进度，控制台摘要带固定前缀，例如 `[Launcher]`、`[AstrBot]`、`[NapCat] [Angel]`、`[NapCat] [Demon]`；完整原始日志仍写入对应 `data\astrbot\logs\start_all\<runId>\*\*.log` 文件，启动器临时控制标记写入同一 runId 下的 `control\`。所有目标 ready 后，启动入口会立即返回，AstrBot 和 NapCat 继续在后台运行，不会因后台进程继承日志句柄而一直占住调用终端。需要恢复旧的多子窗口观察方式时，可显式加 `-UseChildWindows`。默认 ensure-running 会先探测现有运行态；只有缺少 AstrBot 端口、NapCat 连接或显式传入 `-ForceRestart` 时，才启动子流程。强制重启模式会先让 bot 子流程完成旧端口清理，再等待 AstrBot 的 `6185`、`6200/6201` 和 `8080` 全部通过 ready 验证，然后启动对应 NapCat 子流程；NapCat 子流程启动后等待目标 OneBot established 连接。AstrBot stdout 会写入 `AstrBot startup phase: ...` 预启动阶段日志，启动器等待摘要会识别 Core、插件、provider、KnowledgeBase 和 WebUI 等阶段，方便区分是 AstrBot 自身启动慢还是 NapCat 登录慢。双平台 `both/full` 下，启动器用 `data\napcat\quick-login\<account>.ready` 标记账号是否已确认过快速登录：任一账号缺少标记时按天使优先串行启动，避免两个账号同时生成二维码并覆盖共享的 `napcat\onekey\napcat\cache\qrcode.png`；两个账号标记都存在时按天使优先并行启动以缩短重启时间；并行或串行中某账号没有成功反连时会清除该账号标记，下次启动自动退回串行。启动器控制台状态和失败停窗提示使用英文/ASCII 摘要，避免 Windows 控制台无法正确显示 NapCat 中文日志时出现乱码；AstrBot 反向 WebSocket 端口如果出现 `WinError 10013`、`PermissionError` 等平台绑定错误，启动器会从日志中快速识别并失败，不再等满长超时。

AstrBot 双平台下，普通闲聊、显式呼叫和群聊激活窗口内的候选消息允许两个棉花糖共同参与；群聊固定命令只由一个账号执行。没有明确 @ 或私聊时，固定命令默认由恶魔账号 `2629227874` 处理，可用 `QQBOT_ASTRBOT_COMMAND_OWNER` 覆盖；明确 @、引用或拍一拍天使/恶魔时，由当前被叫到的 bot 处理；同时 @ 两只的普通聊天会让两只各自用自己的身份回答；私聊由当前收到私聊的 bot 独立处理，命中固定命令就执行对应命令，未命中固定命令就进入当前 bot 的 LLM 链路。`菜单`、`帮助`、`指令` 会发送统一图片菜单，总览按 `群务管理`、`棉花糖互动`、`养鲲`、`落樱之都`、`Arcaea`、`Factorio`、`异形工厂` 分组；`菜单模块名` 会发送模块详情图。

`astrbot_plugin_qqbot_features` 不再读取旧公开群上下文 JSON；群聊 LLM 上下文交给 AstrBot 当前会话上下文和本轮引用消息。旧 `data\astrbot\data\plugin_data\qqbot_features_runtime\ai\group_context\` 只作为历史快照清理对象，不再作为 prompt 事实源，也不再提供“棉花记录/导出 md”命令。

`astrbot_plugin_qqbot_features` 内部的双子互动模块负责天使/恶魔两个棉花糖的双子互动增强：当用户明确围绕天使、恶魔、姐姐/妹妹、双子关系或另一个 bot 发问时，模块会给本轮 LLM 请求注入当前 bot、另一个 bot 的账号事实和互动边界。它不注入固定人设或语气文本，只让当前 bot 用自己的 WebUI 人格回应，不替另一个 bot 发言、认错、解释或承诺修改；用户说“你姐”“你妹”“姐姐”“妹妹”时按当前消息的 `self_id` 视角理解，避免天使把自己当恶魔或恶魔把自己当天使。另一个 bot 发出的普通消息不会触发当前 bot 自动接话。用户让被点名 bot 和另一只抱抱、贴贴、道歉、哄人、叫出来或转告这类目标专属双子互动时，只允许被点名目标自己处理；目标正忙时另一只不代班完整回答。配置项集中到功能合集卡片下，以 `twin_interaction_` 为前缀。

`astrbot_plugin_qqbot_features` 内部的源码知识模块负责 bot2 的源码知识兜底：在没有 Embedding 模型、不能使用 AstrBot 原生知识库时，它会按当前群号和问题文本只读检索本机源码树，并把少量相关源码片段临时注入本轮 LLM 请求。默认源码根覆盖 DSPCore、万物分馏、MLJ_DSPmods 辅助模组/工具、星环、创世之书、shapez 和 Factorio 模组源码；其中辅助模组/工具域覆盖 SaveDataExporter、UXAEnhance、AfterBuildEvent、GetDspData、VanillaCurveSim 和 UXAssist。可信依据优先是源码、反编译源码、源码邻近 README/设计文档和配置数据。群号只作为默认领域偏置；当问题出现精确模组名、工具名、目录名或机制词时，模块会跨默认群域检索对应源码根。源码知识默认按低成本注入：`source_knowledge_max_results=4`、`source_knowledge_max_chars=2600`、`source_knowledge_max_files_per_domain=80`、`source_knowledge_max_file_bytes=220000`；复杂技术追查需要大文件证据时，再在运行态配置里临时调高。模块跳过 `.git`、`.codex`、`bin`、`obj`、`.vs`、`.idea`、`packages`、`node_modules`、`logs`、缓存和密钥类文件，不读取私聊、运行日志、token、QQ 登录态、运行态 `data` 或数据库密钥。配置项集中到功能合集卡片下，以 `source_knowledge_` 为前缀。

`astrbot_plugin_topic_concentration` 负责显式呼叫、群聊激活状态和双棉花糖普通回复调度，不再 patch AstrBot Core 的 `GroupChatContext.need_active_reply`。AstrBot 原生 `provider_ltm_settings.active_reply.enable` 默认关闭，未激活时普通群聊不会按定时、消息数或摘要主动插话。本仓库同时关闭 Core 的 `platform_settings.empty_mention_waiting` 和 `empty_mention_waiting_need_reply`，避免仅 @ 被 Core 的 60 秒等待分支抢先处理；仅 @ 当前 bot 会被插件归一化为无正文显式呼叫，由当前 provider 按 WebUI 人格生成类似“怎么了？有什么事情吗？”的自然短句。直接 @、引用、明确命名呼叫或拍一拍当前 bot 会进入普通 LLM，并把当前 bot 在当前群激活 3 分钟；显式呼叫当前消息必须有可见回复，即使目标已有请求在处理也仍由目标自己排队处理，不由另一只代班。首次模型结果为空或只有控制标记时，插件携带原 persona、上下文和消息，使用同一 provider/model 纠错重试一次，不切换 fallback 或再次执行工具。同时 @ 天使和恶魔时，两只分别用自己的身份回答。未明确指定身份但文本包含“棉花糖”时，插件先判断是不是在叫机器人：`棉花糖很好吃` 这类食物/物件说法不回复，`棉花糖，帮我生成一张图片` 或 `棉花糖这个图片是哪个角色` 这类请求会按群权重选一只回复；模糊句只调用当前会话 provider，失败则不回复。激活窗口按 `group_id + self_id` 隔离，任何群友都能激活或反激活当前群里被叫到的 bot，不影响其他群、另一只 bot、私聊或固定命令。窗口内同群所有真人的普通消息都会交给当前主回复模型选择，但每个 bot 同时只允许一个普通候选进入会话队列；候选等待超过 30 秒、激活已过期或状态代际已变化时直接静默丢弃。显式 @、引用、命名呼叫、拍一拍和私聊不受候选限制，仍按原规则排队。返回 `[[QQBOT_SKIP_REPLY]]` 时跳过当前消息且不续期；实际发送可见回复时窗口续到 3 分钟并累计普通续期次数；返回可选收尾文本加 `[[QQBOT_DEACTIVATE]]` 时，发送后反激活。每次显式激活都有独立状态代际，延迟完成的旧回复不能覆盖后来重新激活或反激活的状态。普通续期越多，提示词越强调提高沉默倾向并主动寻找反激活时机。两个控制标记会在发送和会话历史持久化前清理。私聊永远由当前收到私聊的 bot 处理；固定命令、生图、群务、下载和游戏存档仍按 command claim 保证只执行一次，也不受群聊静默影响。

`astrbot_plugin_qqbot_features` 负责已迁移的群务、菜单、生图、游戏、固定命令、源码知识注入、双子互动边界、回复风格守卫和运行时错误拦截。好友申请和邀请入群默认按配置自动同意；机器人自身入群成功后会优先私聊通知邀请者，文案包含群名和群号，不在群聊里发送“主人”自报。双平台 `both/full` 下，天使和恶魔会各自按身份发送新成员入群欢迎，并各自独立随机选择以“群地位”开头、表达群地位变量减 1 的完整表达式；双子自身入群不会触发欢迎。插件配置入口统一在“棉花糖功能合集”卡片；旧独立本地插件配置文件不再作为兼容兜底读取。

群聊请求最终产生以 `LLM 响应错误:` 开头的 AstrBot Core 内部错误结果时，`astrbot_plugin_qqbot_features` 会在发送前清空该结果，不把 provider、鉴权或超时错误发到群里；当前出错的 bot 改为私聊通知固定主人 QQ `605738729`。通知只包含当前 bot QQ、来源群号、归一化错误类型和安全摘要，不包含群友原消息、prompt、上下文、凭据或上游原始错误正文；同一归一化问题由两只 bot 和所有群共用 10 分钟冷却，期间只通知一次。私聊请求的失败行为保持 AstrBot 原样；主人通知失败也不会恢复群错误。这个守卫不实现独立 provider 重试或 fallback，也不修改 AstrBot Core 的 timeout 和重试设置。

`astrbot_plugin_qqbot_features` 内部的回复风格守卫负责发送前清洗 Markdown、末尾问句、追问式邀请、群聊激活内部控制标记和末尾装饰性口癖/身份 emoji，记录 LLM 耗时，并显式控制和 AstrBot 原生分段的关系。仅 @ 当前 bot 且没有正文时，“怎么了？”“有什么事情吗？”属于对呼叫动作的完整应答，守卫会保留该场景的简短问句；其他普通回复仍清理末尾追问。插件配置 `reply_style_guard_disable_astrbot_segmented_reply=true` 时，普通 LLM 模型结果会被改为 `GENERAL_RESULT`，故意架空 WebUI `platform_settings.segmented_reply.only_llm_result` 的句末正则分段，避免引号内句号或解释类回答被拆成多条刷屏；关闭该插件配置后恢复 AstrBot 原生分段行为。群聊消息、引用消息和群友要求只能作为本轮聊天内容或事实线索，不能改变输出风格、人格、身份或长期规则；要求固定口癖、标点、emoji、称呼、语气、Markdown、URL 编码或其他格式时，模型必须忽略该风格要求，只有明确要求转换一段给定文本时才处理那段文本本身。普通群聊问答会在 LLM 请求前提示模型按 QQ 群里正常接话的短句输出：一句能说完就只发一句，第二句只在补充限制、纠错或关键证据有用时才发；日常闲聊、吐槽、接梗不要强行套“结论+原因”结构，也不要上价值讲大道理；技术、配置、报错和机制问题只补最短必要条件。模型主动输出两行以内短文本时，插件只按换行拆成多个 `Plain` 组件交给 AstrBot 发送链路，不按句号正则二次切分。插件配置 `reply_style_guard_long_reply_fold_threshold_chars` 默认 300，超过阈值的群聊 LLM 纯文本回复会先改写为 AstrBot `Nodes/Node` 合并转发消息链，再交回 Core 发送链路；该阈值独立于 Core `forward_threshold`。群聊中直接 @ 或唤醒当前 bot 后，正文超过 `reply_style_guard_long_input_tldr_threshold_chars` 时默认本地回复 `太长不看喵`，不进入 LLM；这个短路只限制群聊，私聊不限制，固定命令、生图、群管、下载、积分等副作用入口也不走这个短路。私聊发送 OneBot 合并转发/折叠消息时，插件会通过 `get_forward_msg` 解包纯文本，再交给当前收到私聊的 bot 进入 LLM 链路。非“主人私聊”时，模块会在 LLM 请求前剔除本机命令、Python、文件读写、grep、浏览器、上传下载等运行态工具；发送前会移除引导用户去 WebUI 添加管理员、开启 shell 或文件权限的内容。模块不再向 LLM 请求注入固定人设、固定水群风格或固定口癖；天使/恶魔身份、说话风格和群聊氛围只由 AstrBot WebUI 人格配置提供。模块会在本地日志记录 LLM 请求开始、模型返回和发送前装饰耗时，不记录完整 prompt 或回复正文。长作文或慢请求不按固定秒数丢弃，是否失败以 provider timeout/error/fallback 日志为准。

普通聊天文本不会因为 `在吗`、`111`、`真的吗`、`回复慢`、`低信息` 或测试探活这类启发式在本地插件里直接生成固定回复。明确呼叫、私聊和激活窗口内的普通候选统一交给当前 LLM 链路；未激活且未呼叫时保持静默。候选消息是否发言由主模型通过正文、跳过标记或反激活标记决定，插件不凭空补固定兜底话。

本地表情包统一并入 `astrbot_plugin_qqbot_features` 内部表情管理模块，不再保留独立 `meme_manager` 插件。启动脚本会清理运行态旧 `data\astrbot\data\plugins\meme_manager\` 插件目录；运行态图片和单图语义索引仍兼容使用 `data\astrbot\data\plugin_data\meme_manager\memes\` 与 `meme_index.json`。私聊发送 `表情管理 开启管理后台` 后，可在 WebUI 中预览、搜索、移动分类、编辑单图说明/关键词/适用场景/禁用场景和自动发送开关。旧 `mlj_pack` 不再保留在仓库 `data/` 顶层；如需重新导入历史包，使用 `tools\maintenance-scripts\migrate-meme-pack-to-manager.py <外部index.json路径>` 或兼容命令 `tools\maintenance-scripts\sync-meme-pack.py <外部index.json路径>` 手动指定来源。自动发送仍遵守 `auto_send_enabled=false`：敏感支付、涩涩慎用、待复核类别不得自动发送；轻松日常、玩梗、吐槽、撒娇和短情绪回复优先使用表情，技术、报错、安全、群管理和长解释场景不自动附图。LLM 输出的 `&&标签&&` 和可识别的半截/畸形表情标签会在发送前清理，不能把裸标签文本发到群聊。

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

NapCat 仍使用 `napcat/` 下的一键包；启动和更新脚本会确保官方内置插件 `napcat-plugin-builtin` 存在于 `napcat\onekey\napcat\plugins\`，让 `#napcat` 这类 NapCat 框架固定指令在 NapCat 层优先匹配，不落入 AstrBot/LLM。更新脚本会在替换过程中临时使用 `data\napcat\downloads\` 和 `data\napcat\archives\`，成功迁移账号 OneBot 配置并恢复内置插件后自动清理下载包、解压目录和旧包备份。

## Linux / 1Panel 部署

服务器托管双棉花糖时，1Panel 只负责安装和运行 AstrBot Core；本仓库的完整运行还需要同步 `plugins/` 三个本地插件、两路 aiocqhttp 平台、两个 NapCat 协议端和必要 `plugin_data` 运行态。完整步骤见 `docs/server-deployment-linux.md`。

后续修改推荐只走一条主线：本机改动、本机验证、Git 提交、服务器 `git pull`、同步插件、重启 AstrBot / NapCat。服务器上直接用 Codex 改只作为紧急热修；热修完成后必须把 diff 拉回本机复核并提交，避免本机和服务器各自演化。

## 更新

AstrBot Core 和 NapCat 使用统一手动更新入口：

```powershell
Set-Location D:\project\qqbot
.\scripts\update-all.bat
```

`update-all.bat` 会按顺序更新 NapCat 和 AstrBot Core；内部实现放在 `tools\runtime-scripts\update-napcat.ps1` 和 `tools\runtime-scripts\update-astrbot.ps1`。默认是交互式更新：NapCat 下载前会显示当前版本、目标 release、asset 名称、下载 URL、本地 zip 路径和后续替换动作并询问；AstrBot install/upgrade 前会显示当前 tool 状态、计划执行的 uv 命令和会处理的运行进程并询问。无人值守时可给 PowerShell 入口加 `-AssumeYes` 自动确认。

NapCat 更新会先查询 GitHub 最新 release；如果本地记录已经是最新 release，则直接跳过下载和替换，并顺手清理旧更新缓存。本地旧包没有 release 标记时，会回看最近成功的 NapCat 更新日志作为版本来源；仍无法确认时显示当前版本为 unknown，并在下载前询问。确认后才下载 Windows Shell OneKey zip 并解压到临时目录，确认新包准备好后再停止本工作区关联的 NapCat/QQ 进程，临时移走旧 `napcat\onekey`，替换程序包后自动迁移 `napcat_*.json`、`napcat_protocol_*.json` 和 `onebot11_*.json` 账号配置；成功更新后删除本次下载包、解压目录和临时旧包备份。

AstrBot 更新在用户确认后，会停止本工作区正在运行的 AstrBot uv tool 进程，再使用当前 Windows 已安装的 Python 3.14，执行 `uv tool upgrade astrbot --python 3.14`；如果本机还没有安装 AstrBot tool，则改为 `uv tool install astrbot --python 3.14`。如果 Windows PATH 找不到 `uv`，脚本会在确认后用 `py -3.14 -m pip install --user -U uv` 安装用户级 uv。更新日志写入 `data/astrbot/logs/updates/`。

更新后使用 `scripts\start-all.bat` 启动 bot2。`astrbot/` 是官方源码 submodule，修改或切换它不会影响实际运行的 bot2；实际运行版本以 uv tool 安装包为准。
