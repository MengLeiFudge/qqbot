# QQBot 账号工作区

本仓库维护四个 QQ 账号的启动编排、NapCat、自研插件和官方框架版本。项目中的框架目录由官方发布包生成，实际配置和运行数据各自留在本机。[框架与插件部署](docs/framework-deployment.md)

| Target | 账号 | QQ | OneBot | 框架与职责 |
| --- | --- | --- | --- | --- |
| `yunqi` | 云栖 | `1443944862` | `6201` reverse client | AstrBot，聊天和固定功能 |
| `yelin` | 夜凛 | `2629227874` | `6202` forward server | MaiBot，暂停启动 |
| `lanling` | 蓝铃 | `3600812036` | `6203` forward server | MaiBot，独立聊天、日记与工作区 |
| `fengling` | 风铃 | `3056830689` | `6204` forward server | MaiBot，独立聊天、日记与工作区 |

账号与端口见 [账号清单](napcat/accounts.json)，启用策略与角色关系见 [机器人角色](docs/bot-roles.md)。

## 获取与部署

```powershell
Set-Location D:\project
git clone https://github.com/MengLeiFudge/qqbot.git
Set-Location qqbot
.\scripts\update-all.bat astrbot
.\scripts\update-all.bat maibot
```

首次部署需要恢复或填写各实例的本机配置，并准备 NapCat 与独立 QQ。真实密钥、QQ 登录态、数据库、日志和会话数据均保存在本机。[框架与插件部署](docs/framework-deployment.md) · [NapCat 部署](napcat/README.md)

## 启动

```powershell
.\scripts\start-all.bat all
.\scripts\start-all.bat yunqi
.\scripts\start-all.bat fengling
.\scripts\start-all.bat lanling
```

`all` 启动清单中 `autoStart=true` 的账号。每个账号在独立窗口按现有顺序等待 NapCat、框架和 OneBot 连接，成功后关闭启动窗口，失败时在 `logs/startup/` 查看原因。`-ForceRestart` 只重启框架，复用健康 NapCat 登录。`-SkipInstall` 要求已有依赖环境。首次启动应省略此参数。

## 日常维护

| 工作 | 入口 |
| --- | --- |
| 修改与部署自研插件 | 在 `plugins/` 修改，执行 `.\scripts\deploy-plugins.ps1 <Target>` |
| 应用清单中的官方框架版本 | `.\scripts\update-all.bat astrbot`、`.\scripts\update-all.bat maibot` |
| 人工更新 NapCat 与独立 QQ | `.\scripts\update-all.bat napcat` |
| 提交自有源码和部署描述 | 在 `qqbot` 提交，推送需明确授权 |

版本和实例插件范围见 [部署清单](deployment/frameworks.json)。聊天插件重载、专属能力和工作区规则见 [MaiBot 聊天实例](docs/chat-instances.md)。模型调用约定见 [模型 API 路由](docs/model-routing.md)。
