# QQBot 账号工作区

本仓库是 QQ 账号的总工作区。它只负责账号到框架的映射、框架 fork 的 submodule 指针、NapCat 和根启动/更新编排；AstrBot 与 MaiBot 的 Core、插件、配置、数据、日志和依赖环境分别由各自项目维护。

## 账号拓扑

| Target | 账号 | QQ | OneBot | 当前职责 |
| --- | --- | --- | --- | --- |
| `yunqi` | 云栖 | `1443944862` | `6200` reverse client | AstrBot，聊天和全部固定功能 |
| `yelin` | 夜凛 | `2629227874` | `6201` forward server | MaiBot，暂时停用，保留配置与数据 |
| `xingyao` | 风铃 | `3056830689` | `6202` forward server | MaiBot，独立聊天、日记与工作区 |
| `lanling` | 蓝铃 | `3600812036` | `6204` forward server | MaiBot，独立聊天、日记与工作区 |

非敏感映射真源是 `napcat/accounts.json`，角色说明见 [机器人角色](docs/bot-roles.md)。云栖 AstrBot 使用 WebUI `6185`、artifact API `8080` 和 DSP knowledge API `8081`；夜凛、蓝铃、风铃 MaiBot WebUI 分别为 `8003/8004/8005`，消息服务为 `8020/8021/8022`。风铃保留技术 Target `xingyao`；已注销的 `3109326090` 不再启动或更新。部署入口和启用要求见 [聊天实例配置](docs/chat-instances.md)。

## 目录边界

```text
qqbot/
├── astrbot/          # MengLeiFudge/AstrBot fork submodule，deployment 分支
├── maibot-yelin/     # MengLeiFudge/MaiBot fork submodule，deployment 分支
├── maibot-lanling/   # MengLeiFudge/MaiBot fork submodule，蓝铃独立部署
├── maibot-xingyao/   # 风铃独立 MaiBot 部署，保留历史目录名
├── maibot-yuecheng/  # 注销账号的历史工作树，不再启动或更新
├── napcat/           # NapCat、账号映射及自身脚本
├── scripts/          # 按账号 Target 进行根编排
└── docs/             # 跨项目部署说明
```

`astrbot/` 和四个 `maibot-*/` 工作目录都从自身源码启动，并分别拥有 `.venv`、配置、数据、日志、插件和 `scripts/start.ps1`、`scripts/update.ps1`。根目录不提供框架级 `config/`、`plugins/` 或 `data/`。

`napcat/onekey/` 保存本机 NapCat 包、QQ 登录态和实际 OneBot 配置，`napcat/data/` 保存日志、快速登录标记和更新事务数据；两者均不进入 Git。可提交的账号映射和维护脚本位于 `napcat/accounts.json` 与 `napcat/scripts/`。

## 获取工作区

```powershell
Set-Location D:\project
git clone --recurse-submodules https://github.com/MengLeiFudge/qqbot.git
git -C qqbot submodule update --init --recursive
```

五个 submodule 的 `origin` 指向 MengLeiFudge fork，`upstream` 指向对应的官方 AstrBot 或 MaiBot。日常部署固定在各自 `deployment` 分支采用的稳定 Release，不在启动时自动升级。

真实配置和运行态不会随 Git 克隆。首次部署需要在各子项目内恢复或创建本机配置，并安装 NapCat OneKey 包；不得把 provider key、OneBot token、QQ 登录态、数据库、日志或会话数据加入任何仓库。

## 启动

Windows 用户入口按账号暴露以下 Target：

```powershell
Set-Location D:\project\qqbot
.\scripts\start-all.bat all
.\scripts\start-all.bat yunqi
.\scripts\start-all.bat xingyao
.\scripts\start-all.bat lanling
```

`all` 启动 `napcat/accounts.json` 中 `autoStart=true` 的云栖、风铃和蓝铃，跳过夜凛。云栖按 AstrBot ready 后启动 NapCat 并等待反连；MaiBot 账号先启动各自 NapCat，再启动对应 MaiBot 并等待 adapter 建立连接。根入口为每个账号打开独立启动窗口，等待结束后汇总结果。成功后 QQ/NapCat 窗口隐藏、启动窗口关闭，框架继续写入项目日志；失败或超时保留窗口。主控和账号启动日志位于 `logs/startup/`。扫码和失效登录见 [NapCat 登录说明](napcat/README.md#固定端口)。仅维护某账号 NapCat 时使用 `napcat/scripts/ensure-account.ps1 -Target <账号>`。

PowerShell 入口支持 `-ForceRestart` 和 `-SkipInstall`。日常启动与重启复用各项目已有的 `.venv`，不重复同步或安装依赖；环境缺失时才执行首次安装，`-SkipInstall` 则在环境缺失时直接失败。更新依赖使用对应项目的更新入口或显式 `uv` 安装命令。

重载全部框架实例时执行：

```powershell
.\scripts\start-all.bat all -ForceRestart
```

`-ForceRestart` 只强制重启 AstrBot 和 MaiBot，健康 NapCat 登录继续复用。各账号窗口并行启动，不依赖快速登录标记；NapCat 明确记录 QQ 离线时，只重启该账号一次并重新进入登录流程。仅连接暂未建立时仍等待连接，不循环重启。需要手动重启协议端时，执行 `napcat/scripts/ensure-account.ps1 -Target yunqi -ForceRestart`（夜凛使用 `yelin`，蓝铃使用 `lanling`）。新登录的扫码等待由 NapCat 登录锁串行保护，避免多个账号覆盖共享二维码。

各入口输出阶段耗时，就绪后立即返回，后台框架独立写入原日志。MaiBot 每次启动前仍执行聊天实例插件允许策略，不能跳过。根脚本只分发、等待账号连接并汇总状态，不修改框架配置、不复制插件，也不替框架安装依赖。

## MaiBot 聊天插件边界

夜凛、蓝铃和风铃使用相同的十三个通用插件基础，包含聊天、视觉、历史阅读、日记、工作区、主动联系和回复保护；完整清单见 [聊天实例配置](docs/chat-instances.md)。夜凛与风铃的其余 `qqbot_*` 插件实际配置必须为 `plugin.enabled=false`，启动前执行 `scripts/enforce_chat_only.py`。蓝铃保留自己的专属模块和启用选择，启动前由 `scripts/validate_plugin_config.py` 校验配置。各账号的记忆、日记、文件目录和状态独立。

DSP 物理向量库只由云栖 AstrBot 的 `astrbot_plugin_dsp_knowledge` 持有和增量同步。MaiBot `qqbot_knowledge` 通过 `127.0.0.1:8081` 读取同一组召回、融合与 rerank 结果，再交给各自的聊天模型回答；不会建立第二份 DSP 库。共享服务不可用时，MaiBot 继续普通聊天但不注入 DSP 证据。

云栖是固定功能的唯一运行 owner。AstrBot 仅保留云栖平台，不存在 `both`、`angel`、`demon` profile、双 worker、跨账号 command claim 或忙闲代班。

模型调用的 CPA 路由、官网搜索与嵌入/重排序迁移限制见 [模型 API 路由](docs/model-routing.md)。

## 更新

显式更新入口为：

```powershell
.\scripts\update-all.bat all
.\scripts\update-all.bat astrbot
.\scripts\update-all.bat maibot
.\scripts\update-all.bat napcat
```

框架更新器只在干净的 `deployment` 分支上获取官方最新稳定 Release，合入本地部署分支并同步依赖；NapCat 更新器负责 NapCat 与独立 QQ 的配对更新。更新脚本不会 push。`maibot` 更新 Target 覆盖夜凛、蓝铃和风铃。完成兼容处理并分别提交各工作树后，再在 qqbot 中提交新的 submodule 指针。

NapCat 自动更新使用当前 Windows 用户的计划任务。执行以下命令启用，并立即开始首次检查：

```powershell
.\napcat\scripts\register-auto-update.ps1
```

任务 `QQBot-NapCat-AutoUpdate` 在用户登录期间每小时检查官方最新稳定 Release，并在登录两分钟后检查。可用 `-IntervalMinutes` 调整间隔。每次先选择最新 NapCat，再从该 Release 的支持表内选择能取得并通过校验的尽可能新 Windows x64 QQ 完整构建；较新候选不可用时继续下一候选。两个包准备成功后才停止进程，按 NapCat → 独立 QQ 顺序激活。NapCat 已最新时仍检查 QQ，桌面 QQ 保持独立。所有兼容候选均不可用或发布元数据异常时保留当前组合。选版清单、候选来源、包准备与恢复方法见 [NapCat 维护说明](napcat/README.md#napcat-与独立-qq-更新)。

发布查询、兼容支持表和运行包下载使用 TLS 1.2，沿用 Windows 系统代理与证书验证。临时连接错误最多尝试三次，重试共用原有超时预算；持续失败时保存具体原因和已有的更新暂停状态，等待下一轮检查。

自动更新需要重载正在运行的协议端时，通过根 `scripts/start-all.ps1 -Target all -ForceRestart -SkipInstall -NoPauseOnFailure` 恢复 `autoStart=true` 的账号，夜凛继续停用。更新前没有机器人运行时保持停用。旧运行包保存在 `napcat/data/archives/`；临时事务文件移入根 `.codex/trash/`。激活或重启失败会暂停该版本的自动重试，等待人工查看状态和日志。

查看计划任务、最近结果或移除自动更新：

```powershell
Get-ScheduledTaskInfo -TaskName QQBot-NapCat-AutoUpdate
Get-Content .\napcat\data\updates\napcat.json -Encoding UTF8
.\napcat\scripts\register-auto-update.ps1 -Remove
```

更新日志位于 `napcat/data/logs/updates/`，其中记录重启 PID、截止时间和独立的启动日志。人工运行 `napcat/scripts/update.ps1 -AssumeYes` 可以重试失败版本，完成后使用根启动入口恢复连接。

## Git 提交顺序

1. 在 `astrbot/` 提交本地插件和项目脚本，不修改框架 Core。
2. 在 `maibot-yelin/` 提交夜凛插件和项目脚本，保持账号关闭。
3. 在 `maibot-lanling/` 维护蓝铃部署，在 `maibot-xingyao/` 维护风铃部署；`maibot-yuecheng/` 保留历史。
4. 在根 `qqbot/` 提交 NapCat、账号编排、文档和五个 gitlink。

根仓与五个子仓分别审查和提交。根仓不能提交 submodule 内普通文件，也不能用根 `.gitignore` 代替子项目的敏感数据规则。任何 push 都必须单独明确授权。架构取舍见 `docs/adr/0002-account-superproject.md`。

MaiBot 工作目录共享同一 fork，各自保留本地 `deployment` 分支。获准推送后，夜凛使用 `git -C maibot-yelin push origin HEAD:deployment-yelin`，蓝铃使用 `git -C maibot-lanling push origin HEAD:deployment`，风铃使用 `git -C maibot-xingyao push origin HEAD:deployment-xingyao`。注销账号不再创建或推送部署分支。推送前核对对应远端分支的祖先关系，不覆盖其他实例历史。
