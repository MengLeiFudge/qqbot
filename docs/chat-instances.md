# MaiBot 聊天实例

角色和 QQ 对应以 [机器人角色与框架归属](bot-roles.md) 为准，端口与启动选择由 [账号清单](../napcat/accounts.json) 维护。云栖使用 AstrBot；夜凛、蓝铃、风铃使用各自独立的 MaiBot 工作树。

| 角色 | 工作树 / 技术 Target | OneBot | WebUI | 消息服务 |
| --- | --- | --- | --- | --- |
| 夜凛 | `maibot-yelin/` / `yelin` | 6201 | 8003 | 8020 |
| 蓝铃 | `maibot-lanling/` / `lanling` | 6204 | 8004 | 8021 |
| 风铃 | `maibot-xingyao/` / `xingyao` | 6202 | 8005 | 8022 |

风铃沿用原星遥账号的工作树和连接标识，实际昵称与角色为风铃。QQ `3109326090` 已注销，`maibot-yuecheng/` 只保留历史源码与数据，不再进入账号清单、启动或更新。不要继续排查其登录，也不要把它当作风铃。

三台 MaiBot 对齐基础聊天、拍一拍、只读 DSP 检索、身份核验、视频与历史阅读、联网搜索、回复节奏、连发引用、日记、个人工作区和主动联系。夜凛、风铃的通用允许列表在各自 `scripts/enforce_chat_only.py`，蓝铃保留原有独立配置校验。蓝铃的伴侣关系和专属模块不复制给其他角色。

通用扩展源码各自位于 `plugins/org_orge-8_better-diary`、`qqbot_diary`、`qqbot_workspace`、`qqbot_proactive`、`qqbot_reply_guard`。真实配置不入 Git；部署时分别填写机器人 QQ、身份插件的主人、独立工作区和日记取材私聊，不复制其他账号凭据、数据库或插件状态。夜凛、风铃的日记空间发布默认关闭，定时生成和本地导出继续启用。

个人工作区分别为 `D:/project/lanling`、`D:/project/yelin`、`D:/project/fengling`。工作区工具只向主人私聊开放。没有既有主人私聊时，工具先不注册；真实主人私聊会话建立后，在首次规划请求前经身份配置与公开聊天接口核对会话，保存本机绑定并公开重载插件，随后由 Host 限制会话。详见各自 `plugins/qqbot_workspace/README.md`。

风铃不继承星遥的旧记忆：停止写入后，将原角色数据移至根 `.codex/trash/<timestamp>/`，建立空白角色数据；保留 WebUI 登录配置及本账号健康 NapCat 登录态。归档路径记在本机迁移记录，不提交聊天或运行数据。

图片沿用原生多模态。三台 MaiBot 的入站单张压缩配置统一为 `[visual] handle_oversized_images=true`、`max_image_size_mb=1.0`、`oversized_image_handle_method="compress"`。压缩在聊天 Hook 前尝试，失败保留原图，旧缓存不自动重新压缩；它不是固定 1080p，也不能保证多个图片及历史上下文累计低于插件 16 MiB 单帧上限。不得删除图片、删上下文或改框架私有常量来绕过限制。

风铃的 `chat.reply_timing.planner_interrupt_max_consecutive_count=0`，首条前的补充取消由本地 `cpa_session` 与 `qqbot_reply_timing` 按源发送者处理，取消后通过公开主动任务重新排队；其他群成员插话保留在完整上下文中。维护时核对模型请求、首段等待、重新排队与真实发送记录，ready 不代替聊天验收。

首次部署须由用户阅读并确认本实例 `EULA.md` 与 `PRIVACY.md`，通过框架原生机制保存同意标记；条款更新后重新确认，不复制其他实例的同意标记。后台入口无交互输入，未确认时保持待启动。

本地分支仍为 `deployment`，夜凛、风铃的远端目标分别为 `deployment-yelin`、`deployment-xingyao`，蓝铃为 `deployment`。首次创建远端分支前 Git 可显示 `gone`；不得回退跟踪其他账号。推送需要用户明确授权，并使用对应的明确 refspec，不创建注销账号的远端分支。

日常从根 `scripts/start-all.ps1 -Target all -SkipInstall -NoPauseOnFailure` 启动云栖、蓝铃、风铃，夜凛保持 `autoStart=false`。单独维护风铃可使用 `-Target xingyao`。按既有入口等待 NapCat、WebUI 与适配器连接，不重复启动或循环重启；日志位于根 `logs/startup/`、各工作树 `logs/` 和 `napcat/data/logs/accounts/<Target>/`。
