# 棉花糖功能合集

作者：MengLei

## 插件用途

本插件是 AstrBot 当前固定功能入口，覆盖群务、菜单、生图、美图、复读、戳一戳、养鲲、落樱之都、Arcaea、Factorio 和异形工厂。

普通聊天不在这里硬编码回复。没有命中明确命令、游戏会话答案、协议事件或本地硬安全提醒时，消息应交给 AstrBot LLM 链路。

## 菜单指令

- `菜单` / `帮助` / `指令`
  - 发送统一图片菜单总览。
  - 展示当前分类：群务管理、棉花糖互动、养鲲、落樱之都、Arcaea、Factorio、异形工厂。
- `菜单<分类名>`
  - 发送指定分类详情图。
  - 示例：`菜单棉花糖互动`、`菜单Arcaea`、`菜单群务管理`。

## 群务管理

- `清理群文件` / `群文件清理通知`
  - 作者或机器人自身限定。
  - 扫描超过一周的外层群文件并通知处理。
- `棉花记录 [数量]` / `棉花导出md [数量]`
  - 主人限定，只能在群聊中使用。
  - 从公开群上下文缓存读取最近记录，写入固定目录 `data\astrbot\data\exports\group_notes\`。
  - 兼容“记录一下这个对话的内容到当前目录下 .md格式”这类说法，但不会写入用户指定路径或当前工作目录。
- 好友申请
  - 按配置自动同意 OneBot 好友申请。
- 邀请入群
  - 按配置自动同意 OneBot 邀请入群请求。
  - 机器人自身入群成功后优先私聊通知邀请者，文案包含群名和群号。
- 新成员入群欢迎
  - 在 full 模式下天使和恶魔各自发送符合自身身份的欢迎。
  - 每个 bot 独立随机选择以“群地位”开头、表达群地位变量减 1 的完整表达式；天使和恶魔互相入群不会触发欢迎。

## 棉花糖互动

- `棉花糖生图 [模型名] <提示词>`
  - 提交 RightCodes 生图任务。
  - 支持积分扣除、失败退回、图片结果发送。
  - 生图成功、失败或超时失败都会引用原始生图请求；默认 240 秒总超时，超时后回复失败并退回本次扣除的积分或免费次数。
  - “生成一张 xxx 图片”这类自然语言请求只提示生图指令和积分消耗，不直接执行扣费生图。
- RightCodes 生图接口知识库
  - 用户询问 RightCodes 画图接口、`body`、`size`、`1024x1024`、`/v1/images/generations` 或 `/v1/chat/completions` 时，会在 LLM 请求前注入官方接口资料。
  - 如果用户引用上一条问题后只说“回答一下”，被引用消息会作为当前请求原文参与 RightCodes 知识库判定和 LLM 上下文，不只看当前短句。
  - `POST /v1/images/generations` 支持 `size` 字段，形如 `"1024x1024"`；流式防超时建议走 `/v1/chat/completions` 并设置 `stream=true`。
- `生图模型` / `生图价格`
  - 查看可用模型和消耗说明。
- `查看积分` / `balance` / `points`
  - 查询当前 QQ 的生图当前积分和今日免费状态，不展示历史累计消息数。
- `用量`
  - 查询插件配置的默认 Sub2API 账号 5h / 7d 用量窗口。
  - 该缓存按 Sub2API 账号名全局共享，不按 QQ 用户、群或 bot 身份拆分；所有 QQ 查询的都是同一个默认账号结果。
  - 插件启动后后台定时使用 Sub2API `source=active&force=true` 主动刷新，默认每 300 秒一次；群里发送 `用量` 时只返回最近一次成功缓存，不等待刷新请求。
  - 可配置一个或多个提醒群号；5h 用量首次跨过 80%、90%、95% 时自动提醒，回落到阈值以下后才会再次触发同一阈值。
  - 如果 Sub2API 只返回一个匹配账号，机器人只返回这一条；如果返回多个匹配账号，机器人按接口顺序逐个列出。
- `来点美图` / `色图` / `混合`
  - 调用 Lolicon 图片能力，使用 AstrBot 迁移后的缓存和群配置。
- `开群色图` / `关群色图`
  - 作者限定，控制当前群 R18 权限。
- `开图片显示` / `关图片显示`
  - 作者限定，控制 R18 结果是否直接发图。
- 复读
  - 群里连续出现相同纯文本消息时概率复读，并带冷却。
- 戳一戳
  - 戳当前机器人时按概率发送文本回应。
  - 双 bot 之间不互戳、不跟戳。

## 养鲲

- `摸鲲` / `养鲲` / `抓鲲` / `捕鲲`
  - 创建或获取当前用户的鲲。
- `属性` / `背包` / `商城` / `签到`
  - 查询或操作当前用户存档。
- `等级排行` / `财富排行` / `萌泪币排行`
  - 查看排行榜。
- `挑战` / `进击...` / `boss`
  - 参与战斗玩法。
- `赠送...` / `赠送全部...`
  - 用户间道具或资产转移。

## 落樱之都

- `落樱之都`
  - 查看基础玩法菜单。
- `注册<名字>` / `改名<名字>`
  - 创建或修改角色名。
- `个人信息`
  - 查看当前角色状态。
- `加经验<number>` / `嘤<number>`
  - 基础数值操作。
- `加<number>力量|智力|体质|敏捷|魅力`
  - 角色加点。
- `恢复` / `回复`
  - 恢复当前角色。

## Arcaea

- `arctj10.5`
  - 按 PTT 推荐谱面。
- `archd` / `arctz`
  - 查询当前活动梯子。
- `zm` / `arczm`
  - 开始字母猜歌。
- `qh` / `arcqh`
  - 开始或继续曲绘猜歌。
- `arcqh bt` / `arcqh 补图`
  - 打开下一块曲绘。
- `jx` / `arcjx`
  - 揭晓当前猜歌局。
- `xz` / `arcxz`
  - 作者限定，查询并下载 Arcaea 相关安装包。

## Factorio

- `Factorio下载链接` / `异星下载链接` / `太空时代下载链接`
  - 获取 Factorio Space Age Windows 安装包下载链接。
  - 需要本机配置 Factorio 凭据。

## 源码知识兜底

- LLM 请求前按当前问题检索只读源码树，临时注入少量证据片段；不依赖 AstrBot 原生知识库或 Embedding。
- 默认领域覆盖 DSPCore、万物分馏、MLJ_DSPmods 辅助模组/工具、星环、创世之书、shapez 和 Factorio。
- `dsp-mod-tools` 辅助模组/工具域默认覆盖 SaveDataExporter、UXAEnhance、AfterBuildEvent、GetDspData、VanillaCurveSim 和 UXAssist。
- 群号只作为默认领域偏置；当问题包含精确模组名、工具名、目录名或机制词时，会跨默认群域检索对应源码根。
- 运行态配置里的 `source_knowledge_max_results`、`source_knowledge_max_chars`、`source_knowledge_max_file_bytes` 如果低于插件有效下限，会自动提升到能覆盖大号 `data/strings.json` 说明文件的范围。

## 异形工厂

- `i <短代码>` / `view <短代码>`
  - 渲染 shapez 短代码图片。
- `chart <短代码>`
  - 渲染结构图。
- `path <短代码>`
  - 渲染路径图。
- `p <参数>` / `puzzle <参数>`
  - 在线谜题入口；未配置 shapez token 时提示无法获取。

## 配置项

- `feature_mode`
  - `full`：AstrBot 接管已迁移自动事件。
  - `dual`：仅保留为旧配置兼容，运行时也按 `full` 处理。
  - 环境变量 `QQBOT_ASTRBOT_FEATURE_MODE` 优先。
- `auto_approve_friend_requests`
  - 是否自动同意好友申请，默认开启。
- `auto_approve_group_invites`
  - 是否自动同意邀请入群，默认开启。
- `sub2api_base_url`
  - Sub2API 根地址，例如 `https://ai.example.com`。
- `sub2api_admin_api_key`
  - Sub2API 设置页生成的 `admin-` 开头 Admin API Key，只填写在运行态插件配置，不写入源码或示例配置。
- `sub2api_default_account_name`
  - `用量` 默认查询的 Sub2API 账号名，默认 `Pro`。所有 QQ 和所有群共用这个账号名的后台刷新缓存；若接口返回多个同名或搜索匹配账号，会逐个列出。
- `sub2api_timeout_seconds`
  - Sub2API 主动刷新查询超时秒数，默认 90 秒。
- `sub2api_refresh_interval_seconds`
  - Sub2API 后台刷新间隔秒数，默认 300 秒；最低按 60 秒处理。
- `sub2api_alert_group_ids`
  - Sub2API 5h 用量提醒目标 QQ 群号，英文逗号分隔；留空则不主动提醒。
- `QQBOT_ASTRBOT_COMMAND_OWNER`
  - 双平台 full 模式下固定命令 owner 账号，默认恶魔棉花糖 `2629227874`。

## 双 bot 边界

- 天使账号：`1443944862`。
- 恶魔账号：`2629227874`。
- 主人账号：`605738729`。
- 天使和恶魔发出的消息不会触发本插件固定命令。
- 生图积分、养鲲、落樱、Arcaea 会话等用户数据按用户 QQ 共用，不按 bot 风格拆分。
- 菜单、生图、群务等固定命令不参与 LLM worker 负载均衡；双平台同一消息按目标 @、固定命令 owner 和 canonical claim 只执行一次。claim key 优先使用群号、发送者、当前纯文本、@ 目标、引用消息和时间桶，不依赖双平台可能不一致的 message_id。
- 闲聊、普通问答和可代班的普通 LLM 回复交给 AstrBot LLM 链路，由主动接话/worker 调度层决定当前由哪个棉花糖处理。
- 普通 LLM 请求如果带引用消息，本插件会把“被引用消息 + 当前消息”作为本轮请求原文临时注入，避免“回答一下”这类短句丢失真实问题。

## 数据与安全边界

- 使用 `data\astrbot\data\plugin_data\qqbot_features_runtime` 作为游戏、Arcaea、公开群上下文、RightCodes 积分和本地 artifact 发布状态目录。
- 群聊记录导出只读取公开群上下文 `data\astrbot\data\plugin_data\qqbot_features_runtime\ai\group_context\<群号>.json`，只写固定安全目录，不接受用户传入路径。
- 不提交运行态数据、QQ 登录态、token、数据库或日志。
- RightCodes API Key 直接填写在本插件配置字段 `api_key`，不写入插件源码，也不再读取旧 `.env`。
- Sub2API Admin API Key 直接填写在本插件运行态配置字段 `sub2api_admin_api_key`，不写入插件源码、示例配置、群消息或日志。
