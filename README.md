# QQBot 账号工作区

本仓库是四个 QQ 账号的总工作区。它只负责账号到框架的映射、两个框架 fork 的 submodule 指针、NapCat 和根启动/更新编排；AstrBot 与 MaiBot 的 Core、插件、配置、数据、日志和依赖环境分别由各自项目维护。

## 账号拓扑

| Target | 账号 | QQ | OneBot | 当前职责 |
| --- | --- | --- | --- | --- |
| `yunqi` | 云栖 | `1443944862` | `6200` reverse client | AstrBot，聊天和全部固定功能 |
| `yelin` | 夜凛 | `2629227874` | `6201` forward server | MaiBot，只聊天 |
| 无根 Target | 星遥 | `3056830689` | `6202` forward server | 仅保留 NapCat |
| 无根 Target | 月澄 | `3109326090` | `6203` forward server | 仅保留 NapCat |

非敏感映射真源是 `napcat/accounts.json`。云栖 AstrBot 还使用 WebUI `6185` 和本地 artifact API `8080`；夜凛 MaiBot WebUI 固定为 `8003`。

## 目录边界

```text
qqbot/
├── astrbot/          # MengLeiFudge/AstrBot fork submodule，deployment 分支
├── maibot-yelin/     # MengLeiFudge/MaiBot fork submodule，deployment 分支
├── napcat/           # 四账号 NapCat、账号映射及自身脚本
├── scripts/          # all/yunqi/yelin 根编排
└── docs/             # 跨项目部署说明
```

`astrbot/` 与 `maibot-yelin/` 都从自身源码启动，并分别拥有 `.venv`、配置、数据、日志、插件和 `scripts/start.ps1`、`scripts/update.ps1`。根目录不提供框架级 `config/`、`plugins/` 或 `data/`。

`napcat/onekey/` 保存本机 NapCat 包、QQ 登录态和实际 OneBot 配置，`napcat/data/` 保存日志、快速登录标记和更新事务数据；两者均不进入 Git。可提交的账号映射和维护脚本位于 `napcat/accounts.json` 与 `napcat/scripts/`。

## 获取工作区

```powershell
Set-Location D:\project
git clone --recurse-submodules https://github.com/MengLeiFudge/qqbot.git
git -C qqbot submodule update --init --recursive
```

两个 submodule 的 `origin` 指向 MengLeiFudge fork，`upstream` 分别指向官方 AstrBot 和 MaiBot。日常部署固定在各自 `deployment` 分支采用的稳定 Release，不在启动时自动升级。

真实配置和运行态不会随 Git 克隆。首次部署需要在各子项目内恢复或创建本机配置，并安装 NapCat OneKey 包；不得把 provider key、OneBot token、QQ 登录态、数据库、日志或会话数据加入任何仓库。

## 启动

Windows 用户入口只按账号暴露三个 Target：

```powershell
Set-Location D:\project\qqbot
.\scripts\start-all.bat all
.\scripts\start-all.bat yunqi
.\scripts\start-all.bat yelin
```

`all` 只启动云栖和夜凛。云栖按 AstrBot ready 后启动 NapCat 并等待反连；夜凛先启动 NapCat `6201` 服务，再启动 MaiBot 并等待 adapter 建立连接。根入口为每个账号打开独立启动窗口；首次登录需要扫码时，窗口会保留到登录和 OneBot 连接完成。成功后账号 owned 的 QQ/NapCat 窗口会隐藏，启动窗口自动关闭，后台进程继续写入各项目日志；失败或超时时窗口停留，便于直接查看错误。星遥、月澄不会被根入口自动启动，需要维护其 NapCat 时直接使用 `napcat/scripts/ensure-account.ps1`。

PowerShell 入口支持 `-ForceRestart` 和 `-SkipInstall`。根脚本只分发、等待账号连接并汇总状态，不修改框架配置、不复制插件，也不替框架安装依赖。

## Chat-only 边界

夜凛保留 MaiBot 原生聊天、上下文、记忆、表情和图片理解。第三方插件白名单只有 `napcat_adapter`；18 个 `qqbot_*` 插件保留源码但实际配置必须为 `plugin.enabled=false`。`maibot-yelin/scripts/enforce_chat_only.py` 在 Core 启动前纠正并复核该策略，失败时阻止启动。

云栖是固定功能的唯一运行 owner。AstrBot 仅保留云栖平台，不存在 `both`、`angel`、`demon` profile、双 worker、跨账号 command claim 或忙闲代班。

## 更新

显式更新入口为：

```powershell
.\scripts\update-all.bat all
.\scripts\update-all.bat astrbot
.\scripts\update-all.bat maibot
.\scripts\update-all.bat napcat
```

框架更新器只在干净的 `deployment` 分支上获取各自官方 upstream 的最新稳定 Release，合入本地部署分支并同步项目依赖；NapCat 更新器只维护 NapCat。更新脚本不会 push。完成兼容处理并分别提交两个 fork 后，再在 qqbot 中提交新的 submodule 指针。

## Git 提交顺序

1. 在 `astrbot/` 提交 AstrBot Core 适配、插件和项目脚本。
2. 在 `maibot-yelin/` 提交 MaiBot chat-only 适配、插件和项目脚本。
3. 在根 `qqbot/` 提交 NapCat、账号编排、文档和两个 gitlink。

三个仓库分别审查和提交。根仓不能提交 submodule 内普通文件，也不能用根 `.gitignore` 代替子项目的敏感数据规则。任何 push 都必须单独明确授权。架构取舍见 `docs/adr/0002-account-superproject.md`。
