# 星遥与月澄的聊天实例

星遥、月澄分别使用 `maibot-xingyao/`、`maibot-yuecheng/` 独立 MaiBot 工作树。账号、OneBot 端口和启动选择以 [账号清单](../napcat/accounts.json) 为准；根入口支持 `xingyao`、`yuecheng`，`all` 跳过 `autoStart=false` 的夜凛。

| 实例 | QQ | OneBot | WebUI | 消息服务 |
| --- | --- | --- | --- | --- |
| 星遥 | `3056830689` | `6202` | `8005` | `8022` |
| 月澄 | `3109326090` | `6203` | `8006` | `8023` |

两者插件源码、启用选择和模型配置以夜凛部署为初始来源。启用 `napcat_adapter`、`cpa_session`、`qqbot_poke`、`qqbot_knowledge`、`qqbot_identity`、`qqbot_visual`、`qqbot_web_search`、`qqbot_reply_timing`；其余 `qqbot_*` 与聊天插件管理保持禁用。每次启动执行本实例 `scripts/enforce_chat_only.py`，无法解析或确认禁用时停止启动。

各实例的真实配置位于自己的 `config/`、`plugins/*/config.toml`。模型和插件凭据只在本机保存。建立新实例时只复制所需配置，调整 QQ、显示名、自称、监听端口、NapCat token 和 `connection_id`；适配器的全局禁止发送者名单包含其他机器人账号，避免互相触发。CPA 请求直接携带 `x-opencode-session`，要求见 [模型 API 路由](model-routing.md#opencode-go)。

每个实例单独准备 `.venv`，保留独立的 `data/`、数据库、记忆、日志和 PID。不得复制夜凛或其他账号的运行数据、会话、登录态和记忆。DSP 知识仍通过云栖 `127.0.0.1:8081` 只读查询。

首次部署还需由用户阅读并明确确认本实例的 `EULA.md` 和 `PRIVACY.md`，按框架原生机制保存 `eula.confirmed`、`privacy.confirmed`。未取得用户确认时保留待启动状态；后台入口没有交互输入，直接启动会在条款询问处以 EOF 退出。条款更新后重新确认，不复制其他实例的同意标记。

在 `D:\project\qqbot` 的 PowerShell 中启动：

```powershell
.\scripts\start-all.ps1 -Target xingyao -SkipInstall -NoPauseOnFailure
.\scripts\start-all.ps1 -Target yuecheng -SkipInstall -NoPauseOnFailure
```

先等待对应 NapCat 登录和端口 ready，再启动 MaiBot 并等待 OneBot established。登录要求扫码时，在对应账号窗口扫描最新二维码；保留当前等待流程，不重复启动。查看 `logs/startup/`、各实例 `logs/` 和 `napcat/data/logs/accounts/<Target>/`，确认当前进程的插件加载、启用及连接结果。ready 不代替实际聊天验收。

夜凛暂时停用时保留 `maibot-yelin/` 的配置和数据，`autoStart=false`。恢复时先确认 QQ 账号可用，再将账号清单的 `autoStart` 设为 `true`，使用 `-Target yelin` 启动；不得复制星遥或月澄的记忆覆盖夜凛。
