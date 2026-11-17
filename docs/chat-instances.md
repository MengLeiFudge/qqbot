# 星遥与月澄的聊天实例

星遥、月澄分别使用 `maibot-xingyao/`、`maibot-yuecheng/` 独立 MaiBot 工作树。账号、OneBot 端口和启动选择以 [账号清单](../napcat/accounts.json) 为准；根入口支持 `xingyao`、`yuecheng`，`all` 跳过 `autoStart=false` 的夜凛。

| 实例 | QQ | OneBot | WebUI | 消息服务 |
| --- | --- | --- | --- | --- |
| 星遥 | `3056830689` | `6202` | `8005` | `8022` |
| 月澄 | `3109326090` | `6203` | `8006` | `8023` |

两者插件源码、启用选择和模型配置以夜凛部署为初始来源。启用 `napcat_adapter`、`cpa_session`、`qqbot_poke`、`qqbot_knowledge`、`qqbot_identity`、`qqbot_visual`、`qqbot_web_search`、`qqbot_reply_timing`；其余 `qqbot_*` 与聊天插件管理保持禁用。每次启动执行本实例 `scripts/enforce_chat_only.py`，无法解析或确认禁用时停止启动。

各实例的真实配置位于自己的 `config/`、`plugins/*/config.toml`。模型和插件凭据只在本机保存。建立新实例时只复制所需配置，调整 QQ、显示名、自称、监听端口、NapCat token 和 `connection_id`；适配器的全局禁止发送者名单包含其他机器人账号，避免互相触发。CPA 请求直接携带 `x-opencode-session`，要求见 [模型 API 路由](model-routing.md#opencode-go)。

各实例本地分支均为 `deployment`，星遥、月澄在 `.gitmodules` 的远端分支及本地 `branch.deployment.merge` 分别指向 `deployment-xingyao`、`deployment-yuecheng`。首次创建远端分支前，Git 可能将跟踪目标显示为 `gone`；不要回退跟踪蓝铃使用的 `origin/deployment`。获得推送授权后，分别用明确的 `HEAD:refs/heads/deployment-xingyao`、`HEAD:refs/heads/deployment-yuecheng` 创建或更新各自分支，再核对本地跟踪关系与根 gitlink。

星遥、月澄的 `chat.reply_timing.planner_interrupt_max_consecutive_count` 设为 `0`；首条前的补充取消由各自本地 `cpa_session` 和 `qqbot_reply_timing` 配合处理。群聊只跟踪本轮源消息发送者的补充，其他成员插话保留在原生上下文，不撤销当前答复。取消后由公开主动任务能力重新排队，避免把取消误当成沉默而等待数分钟；行为和必需权限见各实例的 [会话插件说明](../maibot-xingyao/plugins/cpa_session/README.md)。维护时同时核对模型请求、首段等待、重新排队和真实发送记录，不能只核对进程在线。

星遥、月澄通过现有 `[visual]` 配置启用原生入站压缩：`handle_oversized_images = true`、`max_image_size_mb = 1.0`、`oversized_image_handle_method = "compress"`。单张超过 1 MiB 的图片在聊天 Hook 前尝试压缩，较小图片沿用原数据；这不是固定 1080p。压缩失败时框架会记录警告并保留原图，因此该阈值不是无条件的体积保证。已有缓存中的历史图片不会因修改阈值而自动重新压缩。

框架插件通信单帧上限为 16 MiB，多个图片的 Base64 与历史上下文仍可能累计超限；单张压缩阈值不能保证整个请求低于上限。现有 SDK 与运行配置没有完整媒体分帧或共享引用接口，仍需核对实际请求和失败日志；不能通过删除图片、删除上下文或框架私有补丁规避。夜凛停用期间没有同期聊天样本，不能据此判定其不受该限制影响。

每个实例单独准备 `.venv`，保留独立的 `data/`、数据库、记忆、日志和 PID。不得复制夜凛或其他账号的运行数据、会话、登录态和记忆。DSP 知识仍通过云栖 `127.0.0.1:8081` 只读查询。

首次部署还需由用户阅读并明确确认本实例的 `EULA.md` 和 `PRIVACY.md`，按框架原生机制保存 `eula.confirmed`、`privacy.confirmed`。未取得用户确认时保留待启动状态；后台入口没有交互输入，直接启动会在条款询问处以 EOF 退出。条款更新后重新确认，不复制其他实例的同意标记。

在 `D:\project\qqbot` 的 PowerShell 中启动：

```powershell
.\scripts\start-all.ps1 -Target xingyao -SkipInstall -NoPauseOnFailure
.\scripts\start-all.ps1 -Target yuecheng -SkipInstall -NoPauseOnFailure
```

先等待对应 NapCat 登录和端口 ready，再启动 MaiBot 并等待 OneBot established。登录要求扫码时，在对应账号窗口扫描最新二维码；保留当前等待流程，不重复启动。查看 `logs/startup/`、各实例 `logs/` 和 `napcat/data/logs/accounts/<Target>/`，确认当前进程的插件加载、启用及连接结果。ready 不代替实际聊天验收。

夜凛暂时停用时保留 `maibot-yelin/` 的配置和数据，`autoStart=false`。恢复时先确认 QQ 账号可用，再将账号清单的 `autoStart` 设为 `true`，使用 `-Target yelin` 启动；不得复制星遥或月澄的记忆覆盖夜凛。
