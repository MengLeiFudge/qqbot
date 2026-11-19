# MaiBot 聊天实例

角色和 QQ 对应以 [机器人角色与框架归属](bot-roles.md) 为准，端口与启动选择由 [账号清单](../napcat/accounts.json) 维护。云栖使用 AstrBot；夜凛、蓝铃、风铃使用各自独立的 MaiBot 工作树。

| 角色 | 工作树 / 技术 Target | OneBot | WebUI | 消息服务 |
| --- | --- | --- | --- | --- |
| 夜凛 | `maibot-yelin/` / `yelin` | 6202 | 8002 | 8022 |
| 蓝铃 | `maibot-lanling/` / `lanling` | 6203 | 8003 | 8023 |
| 风铃 | `maibot-fengling/` / `fengling` | 6204 | 8004 | 8024 |

NapCat 面板端口为 `6100+n`：云栖 6101、夜凛 6102、蓝铃 6103、风铃 6104，由 `accounts.json` 的 `napcatWebuiPort` 在启动前写入共享 `webui.json`。账号 `3109326090` 已注销，工作树已归档到根 `.codex/trash/`，不再进入账号清单、启动或更新。

三台 MaiBot 对齐基础聊天、拍一拍、只读 DSP 检索、身份核验、视频与历史阅读、联网搜索、回复节奏、连发引用、日记、个人工作区和主动联系。夜凛、风铃的通用允许列表在各自 `scripts/enforce_chat_only.py`，蓝铃保留原有独立配置校验。蓝铃的伴侣关系和专属模块不复制给其他角色。

通用扩展源码各自位于 `plugins/org_orge-8_better-diary`、`qqbot_diary`、`qqbot_workspace`、`qqbot_proactive`、`qqbot_reply_guard`。真实配置不入 Git；部署时分别填写机器人 QQ、身份插件的主人、独立工作区和日记取材私聊，不复制其他账号凭据、数据库或插件状态。夜凛、风铃的日记空间发布默认关闭，定时生成和本地导出继续启用。
蓝铃另有 qqbot_scene：私聊决定回复前注入当前场景，后发生的动作叠加在还没停的事上。

个人工作区分别为 `D:/project/lanling`、`D:/project/yelin`、`D:/project/fengling`。工作区工具只向主人私聊开放。没有既有主人私聊时，工具先不注册；真实主人私聊会话建立后，在首次规划请求前经身份配置与公开聊天接口核对会话，保存本机绑定并公开重载插件，随后由 Host 限制会话。详见各自 `plugins/qqbot_workspace/README.md`。

风铃不继承星遥的旧记忆：停止写入后，将原角色数据移至根 `.codex/trash/<timestamp>/`，建立空白角色数据；保留 WebUI 登录配置及本账号健康 NapCat 登录态。归档路径记在本机迁移记录，不提交聊天或运行数据。

图片沿用原生多模态。三台 MaiBot 的入站单张压缩配置统一为 `[visual] handle_oversized_images=true`、`max_image_size_mb=1.0`、`oversized_image_handle_method="compress"`。压缩在聊天 Hook 前尝试，失败保留原图，旧缓存不自动重新压缩；它不是固定 1080p，也不能保证多个图片及历史上下文累计低于插件 16 MiB 单帧上限。不得删除图片、删上下文或改框架私有常量来绕过限制。

风铃的 `chat.reply_timing.planner_interrupt_max_consecutive_count=0`，首条前的补充取消由本地 `cpa_session` 与 `qqbot_reply_timing` 按源发送者处理，取消后通过公开主动任务重新排队；其他群成员插话保留在完整上下文中。维护时核对模型请求、首段等待、重新排队与真实发送记录，ready 不代替聊天验收。

首次部署须由用户阅读并确认本实例 `EULA.md` 与 `PRIVACY.md`，通过框架原生机制保存同意标记；条款更新后重新确认，不复制其他实例的同意标记。后台入口无交互输入，未确认时保持待启动。

## 插件改动与热重载

改插件不需要重启框架进程，也不需要动 NapCat：

- 云栖（AstrBot）：`astrbot/scripts/start.ps1` 设置 `ASTRBOT_RELOAD=1`，`data/plugins/` 下的 `.py` 改动由框架自己检测并只重载受影响插件；提示词、配置和 `README.md` 改动不会触发，需在 WebUI 插件页手动重载。
- MaiBot：插件运行在各自的 runner 子进程，没有文件监听。在 WebUI 插件页把目标插件“禁用”再“启用”一次，运行时会卸载并重新加载该插件，代码重新导入。QQ 内的 `/pm` 插件管理入口按规则保持禁用，不走聊天命令。
- 只有框架核心、依赖或进程级配置变化才重启框架。重启只停框架进程，NapCat 由 `napcat/scripts/ensure-account.ps1` 复用，不会重新登录。

本地分支名与 `.gitmodules` 声明一致：夜凛 `deployment-yelin`、风铃 `deployment-fengling`、蓝铃 `deployment`，upstream 均指向同名远端分支；不得回退跟踪其他账号。推送需要用户明确授权，推送前核对祖先关系。

日常从根 `scripts/start-all.ps1 -Target all -SkipInstall -NoPauseOnFailure` 启动云栖、蓝铃、风铃，夜凛保持 `autoStart=false`。单独维护风铃可使用 `-Target fengling`。按既有入口等待 NapCat、WebUI 与适配器连接，不重复启动或循环重启；日志位于根 `logs/startup/`、各工作树 `logs/` 和 `napcat/data/logs/accounts/<Target>/`。
