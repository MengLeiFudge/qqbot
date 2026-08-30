# AGENTS.md - QQBot Superproject

本仓库是账号级总工作区，不是 AstrBot 或 MaiBot 的源码 monorepo。默认使用简体中文。

## 仓库职责

- 根 `qqbot`：维护 `astrbot`、`maibot-yelin` 两个 gitlink，维护 `napcat/`、`napcat/accounts.json`、根 `scripts/` 和跨项目文档。
- `astrbot/`：独立的 `MengLeiFudge/AstrBot` fork 工作树，维护云栖 Core、插件、配置示例、项目脚本和项目内运行态。
- `maibot-yelin/`：独立的 `MengLeiFudge/MaiBot` fork 工作树，维护夜凛 Core、插件、chat-only 策略、配置示例、项目脚本和项目内运行态。
- `napcat/`：四个 QQ 账号共享的协议端项目；程序包和实际账号配置保留在本机，非敏感账号映射与维护脚本由根仓跟踪。

根目录不得重新建立框架级 `config/`、`plugins/`、`data/`、虚拟环境或框架内部启动逻辑。根脚本只能读取账号清单、调用子项目入口和汇总 ready 状态。

## 固定账号合同

- 云栖 `1443944862`：AstrBot，OneBot `6200`，负责聊天和全部固定功能。
- 夜凛 `2629227874`：MaiBot，OneBot `6201`，只负责聊天。
- 星遥 `3056830689`：仅 NapCat，OneBot `6202`，不由根入口启动。
- 月澄 `3109326090`：仅 NapCat，OneBot `6203`，不由根入口启动。

根启动 Target 只有 `all`、`yunqi`、`yelin`。框架分配变化时保持 Target 和账号固定端口不变，更新 `napcat/accounts.json` 与对应子项目入口。

## AstrBot 边界

- AstrBot 只绑定云栖，不得恢复 `both/angel/demon` profile、夜凛平台、双 worker、跨账号 command claim、忙闲代班或可选择 command owner。
- 云栖是所有现有固定命令、数据写入、群务和副作用功能的唯一运行 owner。
- 本地插件源码放在 `astrbot/data/plugins/` 的原生位置；真实插件配置、数据库、日志、缓存和 `plugin_data` 不跟踪。
- 行为修改优先使用 AstrBot 配置和现有插件 API；只有无法在项目边界内实现时才讨论 Core 补丁。
- AstrBot 自己的 `scripts/start.ps1` 和 `scripts/update.ps1` 必须可从项目目录独立使用，不依赖根文件。

## MaiBot 边界

- MaiBot 身份固定为夜凛，WebUI `8003`，使用全新 `data/` 和记忆，不复用归档的云栖数据。
- `napcat_adapter` 是唯一允许启用的第三方插件，连接 `127.0.0.1:6201`，`connection_id=yelin`。
- `qqbot_*` 业务插件保留源码，但实际与示例配置的顶层 `plugin.enabled` 必须为 `false`。
- 每次启动 Core 前必须执行 `scripts/enforce_chat_only.py`。无法解析配置或无法确认禁用时必须失败关闭，不得绕过策略启动。
- QQ 内插件管理入口保持禁用，不能通过聊天重新启用业务插件。
- MaiBot 自己的 `scripts/start.ps1` 和 `scripts/update.ps1` 必须可从项目目录独立使用，不依赖根文件。

## 跨框架功能维护

同一固定功能后续需要同时维护 AstrBot 与 MaiBot 两套插件源码：AstrBot 侧运行启用，MaiBot 侧运行禁用。本轮迁移不以此规则补齐历史功能差异。修改时分别进入两个 submodule，在各自项目风格和 API 内完成，不在根目录建立共享源码副本或同步脚本。

## NapCat 边界

- `napcat/accounts.json` 是账号、QQ、固定端口、连接方向和当前框架归属的非敏感真源。
- `napcat/scripts/configure-account.ps1` 将清单落实到本机 `onebot11_<QQ>.json`；不得在其他脚本复制四套端口常量。
- 云栖使用 reverse WebSocket client 连接 AstrBot `ws://127.0.0.1:6200/ws`。
- 夜凛、星遥、月澄分别提供 forward WebSocket server `6201/6202/6203`。
- `napcat/onekey/`、`napcat/data/`、QQ 登录态、token、缓存和日志不进 Git。
- NapCat 启动和更新只由 `napcat/scripts/` 负责；根脚本不得实现包替换或账号进程细节。

## 启动与更新

- 根启动入口是 `scripts/start-all.bat` 或 `scripts/start-all.ps1`。
- 云栖顺序：AstrBot WebUI `6185`、OneBot `6200`、artifact API `8080` ready，再启动云栖 NapCat并等待 established。
- 夜凛顺序：夜凛 NapCat `6201` ready，再启动 MaiBot WebUI `8003` 并等待 adapter established。
- 启动不得自动升级框架。
- 根更新入口只调用三个项目自己的更新脚本。两个 fork 只合入官方最新稳定 Release，不追踪主分支每个提交，更新器不得 push。

## 安全与运行态

不得提交真实 token、API key、Authorization header、QQ 登录态、cookies、数据库、私聊或群聊记录、日志、缓存、PID、临时文件和真实运行配置。配置示例必须脱敏；无法确认字段安全时保持忽略并在文档中说明本机配置方式。

归档和清理使用根 `.codex/trash/<timestamp>/` 的可恢复路径。不要恢复旧 `maibot-yunqi/`、根框架数据目录或 AstrBot 双机器人配置作为日常运行态。

## Git 工作流

- 三个仓库分别检查状态、提交和维护历史；不要从根仓暂存 submodule 内普通文件。
- 两个 fork 使用 `deployment` 分支，`origin` 指向 `MengLeiFudge` fork，`upstream` 指向官方仓库。
- 框架提交完成后，根仓只记录新的 gitlink。
- 未经用户明确批准不得 push，也不得把无关 dirty change 带入提交。

## 验证

遵守会话级验证边界。默认只做精确 diff/配置重读、适用的 Python 编译、PowerShell parser、项目 build 和 LSP；不启动机器人、NapCat、浏览器或网络探针，不运行测试、lint 或 format。环境缺少适用 parser/LSP 时如实记录，不能用运行时启动替代。
