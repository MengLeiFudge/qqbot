# QQBot

基于 `NoneBot2 + OneBot V11 + NapCat` 的 Python QQ 机器人项目。

这个仓库承接旧 `mirai` 机器人的功能迁移，并在 Python 侧补充插件注册、AI 接入、本机管理端和 NapCat 一键启动流程。

开发流程、AI 边界和重启验证规则见 `AGENTS.md`。

## 当前能力

- `NapCat -> OneBot V11 -> NoneBot2` 反向 WebSocket 链路
- 本机管理端：状态查看、重启、全局插件开关、作者权限查看、启动日志查看
- 基础管理：菜单、帮助
- 群管助手：统计超过一周的外层群文件并按大小禁言上传者
- 复读：群里连续出现相同文字消息时概率复读，连续次数越多概率越高；复读后短时间内不重复同一内容
- 群功能：Lolicon 美图
- 游戏/工具插件：异形工厂、Factorio 下载链接、养鲲、Arc、落樱之都
- 好友邀请处理：自动处理好友申请和邀请入群，机器人入群后通知邀请者已加入群聊
- 入群欢迎：新成员入群欢迎，机器人自身入群时发送自我介绍
- 戳一戳响应：作者戳机器人或群成员时按概率响应和反戳
- AI 接入：OpenAI-compatible 多 provider 配置、流式响应、群上下文、全群保守主动介入、领域知识候选、连续短回复、固定身份表达、RightCodes 生图、需求提案

## 目录结构

- `bot.py`：NoneBot2 启动入口
- `src/qqbot/config.py`：环境变量与运行配置
- `src/qqbot/bootstrap.py`：适配器注册、管理端路由、插件加载
- `src/qqbot/plugins/`：NoneBot matcher 与事件处理
- `src/qqbot/features/`：按功能归属的业务服务、持久化、外部客户端和渲染逻辑；AI 对话、长期记忆、领域知识、embedding 和 provider 客户端归入 `features/ai/`
- `src/qqbot/services/`：共享基础设施、迁移期兼容入口和跨功能服务
- `src/qqbot/services/plugin_registry.py`：插件元数据注册表
- `scripts/start_bot.ps1`：NoneBot2 子项目启动入口，通常由根级 `scripts/start-nonebot2.ps1` 调用
- `config/qqbot.toml.example`：非敏感配置示例
- `config/env.example`：敏感信息和本机账号配置示例

## 配置

迁移后配置分三层：

- `D:\project\qqbot\data\nonebot2\config\.env`：敏感信息和本机账号，例如 OneBot token、NapCat QQ、AI API key、Factorio 凭据。
- `D:\project\qqbot\data\nonebot2\config\qqbot.toml`：机器人一般配置、路径、AI provider、默认模型等低频修改项。
- `D:\project\qqbot\data\nonebot2\run\settings\` 和 `D:\project\qqbot\data\nonebot2\run\ai\`：管理端和运行时经常变化的状态，例如全局插件开关、AI 对话上下文。

可提交模板：

- `config/env.example`
- `config/qqbot.toml.example`

不要再使用 `nonebot2\.env`、`nonebot2\.env.example` 或 `nonebot2\config\qqbot.toml` 作为运行入口。

最小 `.env` 配置：

```text
QQBOT_ONEBOT_ACCESS_TOKEN=你的 OneBot token
QQBOT_NAPCAT_QQ=你的机器人 QQ
QQBOT_AI_KEY_CODEX_EVERYWHERE=你的 Codex Everywhere API Key
QQBOT_AI_KEY_OPENROUTER_ICU=你的 OpenRouter ICU API Key
QQBOT_AI_KEY_RIGHTCODES=你的 RightCodes API Key
FACTORIO_USERNAME=你的 Factorio 用户名
FACTORIO_TOKEN=你的 Factorio 官网 token
```

AI provider 示例：

```toml
[ai]
default_profile = "codex-everywhere"
max_context_messages = 12
group_context_messages = 30
show_metrics = false
bot_name = "QQBot"

[ai.providers.codex-everywhere]
enabled = true
provider = "openai_compatible"
base_url = "https://codex-everywhere.com/v1"
model = "gpt-5.4-mini"
api_key_env = "QQBOT_AI_KEY_CODEX_EVERYWHERE"
timeout_seconds = 45
max_output_tokens = 4096

[ai.providers.openrouter-icu]
enabled = true
provider = "openai_compatible"
base_url = "https://rehdasu.cn/v1"
model = "gpt-5.4-mini"
api_key_env = "QQBOT_AI_KEY_OPENROUTER_ICU"
timeout_seconds = 45
max_output_tokens = 4096

```

普通 GPT 文本调用只按 `data/nonebot2/config/qqbot.toml` 的 `[ai].default_profile` 和 `[ai.providers]` 决定当前模型与 fallback 顺序；`data/nonebot2/run/settings/ai.json`、私聊“切换AI”命令和管理端都不能覆盖模型选择。管理端“AI 模型”只读展示当前配置来源，修改模型或顺序后必须重启 bot1 才会生效。AI 没有总启停开关，配置 provider/API key 后直接接入。

群聊普通 AI 对话不需要每群开关；所有群都会先把明确求助、提到机器人、领域问题、安全风险或上下文追问识别为候选。普通非 @ 候选会先按群缓冲一小段会话，再由 AI 结合最近聊天窗口、具体话题簇和短期高兴趣话题判断是否介入；这里的话题不是求助词、诊断词或领域词的代码评分，而是“图灵完备里面线路怎么接”“某种分馏塔怎么用”这类具体聊天类型。普通闲聊、玩笑续梗、低信息短句、群友已说清楚的内容、其他 bot 输出或让别人呼叫棉花糖的消息会静默；AI 判定失败也会静默。@ 机器人、点名机器人、生图命令和敏感凭据风险提醒会即时处理。主动介入可以回复最近一段群聊整体，并按场景决定是否引用最关键的触发消息；目标消息在最近 5 条群消息内时直接发文本，不引用也不 @，较早消息才引用并 @ 发言者以避免指向不清。同一轮等待期间积压的后续回复不再继续引用同一条旧消息。低信息闲聊优先一句短消息，通常 40 字以内；已经形成的话题讨论、解释、澄清、技术、配置和报错问题不强行压到 40 字，也不写标题、列表、分节、空行或末尾总结。普通回复、主动介入和拒答都不会用反问或“如果你愿意”“要的话”“你把具体名字发我”“我可以再帮你”这类追问式收尾；能答就直接给结论，不能答就给合法可执行替代。所有群聊和私聊会话都不做危机处理；自述、倒霉、考试迟到、没吃饭、没睡觉等默认按玩笑、夸张、钓机器人、抱怨或时间梗分析，分析不出发言原因时不回答。复杂问题、数学/推理问题和强领域关联问题会优先保证准确性，但不会先发“我先看看”这类占位消息。如果等待期间群友已经给出一致答案，机器人会引用该答案并短确认，避免重复刷屏。AI 文本被切成多条连续回复时，第一条立即发送，后续每条使用较短阅读间隔，通常 1.2 到 3 秒。

普通短 AI 回复会按 `D:\project\qqbot\data\memes\mlj_pack\index.json` 的语义索引和同群冷却，概率性追加 0-1 张本地表情包；短情绪闲聊也允许只发一张表情不带文字。技术、报错、安全、群管理、凭据提醒和长解释场景不自动附图；敏感支付、涩涩慎用、待复核类别不参与自动发送。

RightCodes 生图按 QQ 号全群累计消息积分：群里每发 1 条消息增加 1 积分，积分记录在运行态 `data\nonebot2\run\ai\draw_points.json`。每个 QQ 每天有 1 次 `gpt-image-2` 免费生图；之后按模型价格扣除 `价格 x 500` 积分，默认 `gpt-image-2` 扣 20 积分，`gpt-image-2-vip` 扣 65 积分，`nano-banana` 扣 70 积分，`nano-banana-2` 扣 60 积分，`nano-banana-pro` 扣 90 积分。生成失败或没有返回图片时会退回本次免费次数或已扣积分。私聊或群内 @机器人 发送 `查看积分`、`查询积分`、`查积分`、`积分`、`生图积分` 或 `balance` 可以查看当前 QQ 的生图积分、累计消息数和今日免费状态。普通聊天不能手动加分、扣分或改分。

群聊中出现索要或分享 `.kube/config`、`auth.json`、`credentials`、`token`、API key 等登录凭据和工具认证配置时，机器人会直接提醒不要公开发送、建议撤回并轮换相关凭据。技术排查、群管理和安全提醒会优先使用中性可执行表述，减少口癖和玩笑；对昵称来源、地域口音、编号原因或个人动机没有可见证据时不会猜测归因。

领域群会优先按既有可信知识和候选知识回答；没有足够项目证据时会说明证据不足，不按通用机制补猜。绑定领域群里的普通闲聊不会只因为“怎么、原理、为什么”这类泛疑问词进入重型处理，必须同时命中对应模组术语、领域对象或明确项目别名。

作者在群内 @机器人 发送 `通知清理文件`，会检测当前群的群文件最外层文件。文件夹内文件不处罚；最外层超过一周的旧文件会按上传者汇总到群内，按总大小降序分批 @ 提醒。每条名单消息成功发出后，会立即按 `1 MB = 禁言 1 分钟` 的规则禁言该条名单内对应成员；换算后小于 1 分钟的不禁言。该功能不发送私聊提醒，也不通过私聊触发解禁。

机器人固定身份是猫娘棉花糖；当前 `1443944862` 是天使棉花糖姐姐，主人是萌泪酱（605738729）。群聊或私聊要求修改身份、固定风格、查询其他设定或设置口吻时不会写入长期偏好，也不会读取旧偏好继续影响回复。

长期知识分为可信知识和候选知识。管理端“长期记忆”页可以触发知识候选扫描、查看待处理 AI 任务，并维护可信事实；候选知识不会因为普通群聊一句话直接变成可信事实。

AI 对话只提供文字回复，不再提供语音/文本回复模式设置。小米 MiMo 对话和 TTS 已停用；后续接入新的 TTS provider 前，不会再调用小米转语音。

## 启动

迁移后的日常启动从 monorepo 根目录执行，根脚本会注入 `QQBOT_CONFIG_FILE`、`QQBOT_DATA_ROOT` 和 `QQBOT_VENV_PATH`：

```powershell
Set-Location D:\project\qqbot
.\scripts\start-nonebot2.ps1
```

统一启动 NoneBot2、AstrBot 和 NapCat 时，使用 monorepo 根目录脚本：

```powershell
Set-Location D:\project\qqbot
.\scripts\start-all.bat
```

单独启动 qqbot：

```powershell
Set-Location D:\project\qqbot
.\scripts\start-nonebot2.ps1
```

单独启动 NapCat：

```powershell
Set-Location D:\project\qqbot
.\scripts\start-napcat.ps1
```

NapCat OneBot V11 反连地址：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

## 本机管理端

机器人启动后打开：

```text
http://127.0.0.1:8080/admin
```

管理端只面向本机访问，支持：

- 查看 qqbot / OneBot 连接状态
- 重启 Bot
- 只读查看当前 AI 模型和普通 GPT provider 调用顺序
- 查看和切换全局插件开关
- 只读查看作者权限
- 查看 `data/nonebot2/logs/` 下的启动日志

## 常用命令入口

- `菜单` / `帮助` / `指令`
- `菜单Arc` / `菜单群管助手`：按模块名称或别名查看插件菜单
- `开群色图` / `关群色图` / `开图片显示` / `关图片显示`
- `来点色图` / `美图 凯露 10`
- `arctj10.5` / `zm` / `开*` / `10骨折光` / `猜 骨折光` / `arcqh` / `jx` / `archd` / `xz`
- `Factorio下载链接` / `异星下载链接`：获取 Space Age Windows 安装包下载链接；获取到了就发链接，没获取到就说明失败原因
- `i CrRgSbWy` / `view CrRgSbWy` / `chart CrRgSbWy` / `path RuRuRuRu`
- `养鲲` / `属性` / `等级排行` / `财富排行` / `背包` / `商城` / `签到` / `boss` / `挑战`
- `注册樱花勇者` / `个人信息` / `加经验500` / `加5力量` / `恢复`

Lolicon 美图使用 `https://api.lolicon.app/setu/v2` 获取图片信息，并把 PID、页码、作者、r18、尺寸、tags、扩展名、aiType、uploadDate、原始 URL 和本地路径写入 `data/nonebot2/run/data/lolicon/lolicon.sqlite3`。图片缓存优先复用旧平铺目录 `data/nonebot2/run/data/lolicon/img/{pid}.{ext}`；新下载图片按 `img/r18/` 和 `img/non-r18/` 分类保存，已有本地文件时不会重复下载。

## Arc 插件

Arc 用户入口统一在 `src/qqbot/plugins/arc.py`：

- `arctj10.5`：按 PTT 推荐谱面
- `zm` / `zm5`：开始字符猜歌
- `开x` / `10曲名` / `猜 xxx`：猜歌交互
- `arcqh` / `qh`：开始或继续曲绘切片猜歌
- `jx` / `arcjx`：结束当前群内 Arc 猜歌并公布答案
- `xz` / `arcxz`：查询并下载官网最新 c 版安装包

运行状态主要落在：

- `run/data/arc/guess_sessions.json`
- `run/data/arc/guess_aliases.json`
