# MaiBot 聊天实例

四个账号分别使用独立的 MaiBot 运行目录。角色和 QQ 见 [机器人角色与框架归属](bot-roles.md)，端口与启动选择见 [账号清单](../napcat/accounts.json)。

| 角色 | 运行目录 / 技术 Target | OneBot | WebUI | 消息服务 |
| --- | --- | --- | --- | --- |
| 云栖 | `maibot-yunqi/` / `yunqi` | 6201 | 8001 | 8021 |
| 夜凛 | `maibot-yelin/` / `yelin` | 6202 | 8002 | 8022 |
| 蓝铃 | `maibot-lanling/` / `lanling` | 6203 | 8003 | 8023 |
| 风铃 | `maibot-fengling/` / `fengling` | 6204 | 8004 | 8024 |

NapCat 面板端口为 `6100+n`：云栖 6101、夜凛 6102、蓝铃 6103、风铃 6104，由 `accounts.json` 的 `napcatWebuiPort` 在启动前写入共享 `webui.json`。账号 `3109326090` 已注销，工作树已归档到根 `.codex/trash/`，不再进入账号清单、启动或更新。

夜凛、蓝铃和风铃对齐基础聊天、拍一拍、只读 DSP 检索、身份核验、视频与历史阅读、联网搜索、回复节奏、连发引用、日记、个人工作区和主动联系。夜凛、风铃的通用允许列表在 `scripts/frameworks/enforce_chat_only.py`，云栖、蓝铃沿用本机插件启用选择。

云栖接收 QQ 已送达的所有私聊和所在群的消息。本机 `plugins/napcat_adapter/config.toml` 的 `[chat].enable_chat_list_filter` 显式设为 `false`。普通聊天沿用 MaiBot 的接话规则，指令沿用各自的权限检查。

云栖维护固定指令和 `8080` 产物发布、`8081` 共享 DSP 检索。人工表情审核继续使用 `http://127.0.0.1:8799/`，当前由独立的 `.codex/drafts/review_server.py` 提供。云栖的 `qqbot_meme` 与审核网页共用 `data/shared/meme_manager/`。旧 AstrBot 图库路径通过目录联接指向这份图库，审核工具仍使用 AstrBot 的 Python 环境。

表情包必须由主人逐张批准后才能用于自动发送：新图只落 `inbox/<分类>/` 待批准区，不写索引、不参与选图；审核页 `只看待批准` 里点「批准入库」才进入分类并恢复描述与分数。任何自动收藏不得直接写库。

通用扩展源码集中维护，源目录见 `plugins/maibot/org_orge-8_better-diary`、`qqbot_diary`、`qqbot_workspace`、`qqbot_proactive`、`qqbot_reply_guard`。真实配置不入 Git。部署时分别填写机器人 QQ、身份插件的主人和独立工作区，各账号使用自己的凭据、数据库和插件状态。
蓝铃另有 qqbot_scene：私聊决定回复前注入当前场景，后发生的动作叠加在还没停的事上。

### 日记与工作区

四个账号均启用 better-diary 和 `qqbot_diary`。better-diary 在本机时间 23:30 从各自与主人的私聊取材，素材达到最低要求时生成日记，将当日成品发到自己的 QQ 空间。公开日记使用专门的写作规则，省略私聊原话、个人身份、亲密和健康隐私。历史补写只存档。`qqbot_diary` 将已生成正文导出到对应的 `data/<Target>/workspace/日记/better-diary/`。配置见[日记示例](../deployment/maibot/config-examples/better-diary.example.toml)。生效后核对两插件加载日志、工作区文件和定时发布结果。

各账号的个人工作区在 `data/<Target>/workspace/`，包含笔记、日程和导出的日记文件。聊天数据库、记忆和插件原始存档可从 `data/<Target>/maibot/` 查看，实际由相应实例保存。详见[本机数据布局](framework-deployment.md#本机数据)。

工作区工具只向主人私聊开放。没有既有主人私聊时，工具先不注册；真实主人私聊会话建立后，在首次规划请求前经身份配置与公开聊天接口核对会话，保存本机绑定并公开重载插件，随后由 Host 限制会话。详见 [`qqbot_workspace` 插件说明](../plugins/maibot/qqbot_workspace/README.md)。

风铃不继承星遥的旧记忆：停止写入后，将原角色数据移至根 `.codex/trash/<timestamp>/`，建立空白角色数据；保留 WebUI 登录配置及本账号健康 NapCat 登录态。归档路径记在本机迁移记录，不提交聊天或运行数据。

图片沿用原生多模态。MaiBot 实例的入站单张压缩配置为 `[visual] handle_oversized_images=true`、`max_image_size_mb=1.0`、`oversized_image_handle_method="compress"`。压缩在聊天 Hook 前尝试，失败保留原图，旧缓存不自动重新压缩。多张图片与历史上下文仍可能触及插件单帧上限。不得删除图片、删上下文或改框架私有常量来绕过限制。

四个账号的 `chat.reply_timing.planner_interrupt_max_consecutive_count` 均设为 `0`。聊天补充由本地 [`cpa_session`](../plugins/maibot/cpa_session/README.md) 和 [`qqbot_reply_timing`](../plugins/maibot/qqbot_reply_timing/README.md) 按本轮源消息或实际回复目标的发送者处理。维护时用同人连发、其他群友插话和首段已发三种情况核对实际重排队与发送记录。

首次部署须由用户阅读并确认本实例 `EULA.md` 与 `PRIVACY.md`，通过框架原生机制保存同意标记；条款更新后重新确认，不复制其他实例的同意标记。后台入口无交互输入，未确认时保持待启动。

## 插件改动与热重载

MaiBot 插件运行在各自的 runner 子进程。在 WebUI 插件页将插件禁用再启用一次，运行时会卸载并重新加载插件，代码会重新导入。QQ 内的 `/pm` 插件管理入口保持禁用。

只有框架核心、依赖或进程级配置变化才重启框架。重启只停框架进程，NapCat 由 `napcat/scripts/ensure-account.ps1` 复用。

框架版本和插件部署命令见 [框架与插件部署](framework-deployment.md)。

日常从根 `scripts/start-all.ps1 -Target all -SkipInstall -NoPauseOnFailure` 启动云栖、蓝铃、风铃，夜凛保持 `autoStart=false`。单独维护风铃可使用 `-Target fengling`。按既有入口等待 NapCat、WebUI 与适配器连接，不重复启动或循环重启；日志位于根 `logs/startup/`、各工作树 `logs/` 和 `napcat/data/logs/accounts/<Target>/`。
