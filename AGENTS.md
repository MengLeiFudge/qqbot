# AGENTS.md - QQBot Superproject

本仓库是账号级总工作区，不是 AstrBot 或 MaiBot 的源码 monorepo。默认使用简体中文。

现行机器人名单、角色关系、框架归属与停用要求以 [机器人角色与框架归属](docs/bot-roles.md) 为准；维护前必须先读。下文旧角色名和历史工作树用于定位既有部署，不能覆盖新名单，也不能作为恢复旧账号自动启动或复制旧角色关系的依据。

## 框架核心边界（必须遵守）

- 本规则适用于 AstrBot、MaiBot 以及以后接入的任何框架：禁止为本项目功能、修复或优化直接修改框架核心源码、内置模块或已安装的框架包。
- 行为实现只能放在本地插件中，通过框架公开的插件 API、Hook 和现有配置项间接影响框架；不得把业务逻辑写入 Core，也不得通过修改安装目录绕过此限制。
- 现有扩展能力不足时，先说明限制并在插件边界内调整方案；不得以修复缺陷、兼容或性能需要为由自行改 Core。官方版本更新仍按既有更新流程执行，不借更新加入私有 Core 补丁。
- 此边界同时约束所有框架子项目的实现方式；子项目文档中较宽松的 Core 修改说明不能覆盖本规则。
- 任何机器人都不得为节约 AI token、模型费用或提速而克扣读消息能力，包括将可读图片改成空占位再交给模型。相关性只影响何时触发；暂缓消息应完整保留，触发时携带近期上下文，并允许 AI 主动查阅更早历史。维护消息入口、上下文和速度前先读 [消息完整性与按需触发](docs/message-context.md)。

## 仓库职责

- 根 `qqbot`：维护 `astrbot`、`maibot-yelin`、`maibot-lanling`、`maibot-xingyao`、`maibot-yuecheng` 五个 gitlink，维护 `napcat/`、`napcat/accounts.json`、根 `scripts/` 和跨项目文档。
- `astrbot/`：独立的 `MengLeiFudge/AstrBot` fork 工作树，维护云栖 Core、插件、配置示例、项目脚本和项目内运行态。
- `maibot-yelin/`：夜凛独立工作树，暂时停用并保留配置与数据。
- `maibot-xingyao/`、`maibot-yuecheng/`：星遥、月澄独立 MaiBot 工作树，沿用夜凛的插件与启用策略，分别维护自己的配置、环境和运行态。
- `maibot-lanling/`：独立的 `MengLeiFudge/MaiBot` fork 工作树，维护蓝铃独立部署、插件启用配置及运行态，不参与棉花糖家族插件同步。
- `napcat/`：五个 QQ 账号共享的协议端项目；程序包和实际账号配置保留在本机，非敏感账号映射与维护脚本由根仓跟踪。

根目录不得重新建立框架级 `config/`、`plugins/`、`data/`、虚拟环境或框架内部启动逻辑。根脚本只能读取账号清单、调用子项目入口和汇总 ready 状态。

## 固定账号合同

- 云栖 `1443944862`：AstrBot，OneBot `6200`，负责聊天和全部固定功能。
- 夜凛 `2629227874`：MaiBot，OneBot `6201`，暂时关闭，`autoStart=false`。
- 星遥 `3056830689`：MaiBot，OneBot `6202`，负责聊天、拍一拍和只读知识问答。
- 月澄 `3109326090`：MaiBot，OneBot `6203`，负责聊天、拍一拍和只读知识问答。
- 蓝铃 `3600812036`：MaiBot，OneBot `6204`，负责聊天、拍一拍和只读知识问答。

根启动 Target 为 `all`、`yunqi`、`yelin`、`xingyao`、`yuecheng`、`lanling`；`all` 只启动清单中 `autoStart=true` 的账号。框架分配变化时保持 Target 和账号固定端口不变，更新 `napcat/accounts.json` 与对应子项目入口。

## AstrBot 边界

- AstrBot 只绑定云栖，不得恢复 `both/angel/demon` profile、夜凛平台、双 worker、跨账号 command claim、忙闲代班或可选择 command owner。
- 在棉花糖家族内，云栖是所有现有固定命令、数据写入、群务和副作用功能的唯一运行 owner。
- 本地插件源码放在 `astrbot/data/plugins/` 的原生位置；真实插件配置、数据库、日志、缓存和 `plugin_data` 不跟踪。
- 行为调整必须遵守“框架核心边界”，通过现有配置和本地插件 API 实现，禁止直接修改 AstrBot Core。模型 API 路由维护先读 `docs/model-routing.md`。
- AstrBot 自己的 `scripts/start.ps1` 和 `scripts/update.ps1` 必须可从项目目录独立使用，不依赖根文件。

## MaiBot 边界

- MaiBot 的夜凛、蓝铃、星遥、月澄分别使用独立工作目录，WebUI 为 `8003/8004/8005/8006`，消息服务为 `8020/8021/8022/8023`。各自配置、虚拟环境、`data/` 和记忆独立，不复制其他账号的运行数据。星遥、月澄的部署与插件边界见 `docs/chat-instances.md`。
- 夜凛 `napcat_adapter` 连接 `127.0.0.1:6201`，`connection_id=yelin`；蓝铃连接 `127.0.0.1:6204`，`connection_id=lanling`；星遥和月澄分别连接 `6202/6203`，`connection_id=xingyao/yuecheng`。夜凛、星遥与月澄允许启用 `qqbot_poke`、`qqbot_knowledge`、`qqbot_identity`、`qqbot_visual`、`qqbot_web_search` 与 `qqbot_reply_timing` 六个聊天辅助插件。
- `qqbot_knowledge` 只通过 `127.0.0.1:8081` 使用云栖持有的 DSP 向量检索结果，不在 MaiBot 侧建立额外 DSP 索引；云栖不可用时退回无 DSP 证据的普通聊天。
- 夜凛、星遥与月澄除上述六个聊天辅助插件外，其余 `qqbot_*` 业务插件的实际与示例配置顶层 `plugin.enabled` 必须为 `false`。
- 夜凛、星遥与月澄每次启动 Core 前必须执行 `scripts/enforce_chat_only.py`。无法解析配置或无法确认禁用时必须失败关闭，不得绕过策略启动。
- 蓝铃作为独立 bot 维护插件源码与启用配置，不套用家族插件同步或夜凛允许列表。启动前执行本项目 `scripts/validate_plugin_config.py`，配置无效时停止；不得自动改写插件启用选择。
- 夜凛、星遥与月澄的 QQ 内插件管理入口保持禁用，不能通过聊天重新启用家族业务插件。
- MaiBot 自己的 `scripts/start.ps1` 和 `scripts/update.ps1` 必须可从项目目录独立使用，不依赖根文件。
- 所有框架的首条公开答复等待、后续分段速度及阶段研究遵守 `docs/model-routing.md` 的“回复耗时排查”合同；只在本地聊天插件中实现。

## 跨框架功能维护

本节的插件同步及统一启用合同仅适用于棉花糖家族，目前在云栖（AstrBot）与夜凛、星遥、月澄（MaiBot）之间维护。蓝铃是独立 bot，不参与这套同步与启用合同。

家族内同一有副作用的固定功能后续需要同时维护云栖和家族 MaiBot 实例的插件源码：云栖侧运行启用，MaiBot 侧运行禁用。只读辅助能力可以按明确合同例外：拍一拍由两框架各自插件处理；DSP 知识由 AstrBot 维护唯一物理向量库，MaiBot 只调用 localhost 检索接口。本轮迁移不以此规则补齐其他历史功能差异。修改时分别进入对应框架 submodule，在各自项目风格和 API 内完成，不在根目录建立共享源码副本或同步脚本。

## NapCat 边界

- `napcat/accounts.json` 是账号、QQ、固定端口、连接方向和当前框架归属的非敏感真源。
- `napcat/scripts/configure-account.ps1` 将清单落实到本机 `onebot11_<QQ>.json`；不得在其他脚本复制账号端口常量。
- 云栖使用 reverse WebSocket client 连接 AstrBot `ws://127.0.0.1:6200/ws`。
- 夜凛、星遥、月澄、蓝铃分别提供 forward WebSocket server `6201/6202/6203/6204`。
- `napcat/onekey/`、`napcat/data/`、QQ 登录态、token、缓存和日志不进 Git。
- NapCat 启动和更新只由 `napcat/scripts/` 负责；根脚本不得实现包替换或账号进程细节。维护前读取 `napcat/README.md` 的独立 QQ 与配对更新说明。
- 机器人使用项目内独立 QQ，禁止回退桌面 QQ。手动和定时更新均先选择 NapCat 最新稳定 Release，再在其支持表内按版本从新到旧选择能够取得、校验并准备成功的 Windows x64 完整 QQ 构建；来源包括已有独立运行包、本地缓存、QQ 官网和官方 OneKey 包提供的下载地址。较新候选不可用时继续选择下一项，包准备成功后按 NapCat→QQ 顺序激活。所有兼容候选均不可用或发布元数据异常时保留原组合并报告原因。

## 启动与更新

- 根启动入口是 `scripts/start-all.bat` 或 `scripts/start-all.ps1`。
- 修改代码、插件或配置后，若需要重启机器人才能生效，自动执行一轮重启，不再为该生效步骤重复请求确认。默认重启 `autoStart=true` 的账号，即使只修改了其中一个；用户当轮明确指定只重启一个或不要重启时，按用户要求执行。
- 变更后的重启复用 `scripts/start-all.ps1 -Target all -ForceRestart -SkipInstall -NoPauseOnFailure` 及其子项目入口，保留既有健康 NapCat 登录态，保持 `autoStart=false` 的夜凛关闭。记录启动截止、PID、日志和 ready/连接结果；失败或超时先确认当前状态并报告，不循环重启。
- 云栖顺序：AstrBot WebUI `6185`、OneBot `6200`、artifact API `8080` 和 DSP knowledge API `8081` ready，再启动云栖 NapCat并等待 established。
- MaiBot 账号先等待各自 NapCat ready，再启动对应 WebUI 并等待 adapter established；端口映射见固定账号合同。
- 启动不得自动升级框架。
- 根更新入口只调用各子项目自己的更新脚本。`maibot` 更新 Target 覆盖夜凛、蓝铃、星遥和月澄。框架 fork 只合入官方最新稳定 Release，不追踪主分支每个提交，更新器不得 push。

## 安全与运行态

不得提交真实 token、API key、Authorization header、QQ 登录态、cookies、数据库、私聊或群聊记录、日志、缓存、PID、临时文件和真实运行配置。配置示例必须脱敏；无法确认字段安全时保持忽略并在文档中说明本机配置方式。

归档和清理使用根 `.codex/trash/<timestamp>/` 的可恢复路径。不要恢复旧 `maibot-yunqi/`、根框架数据目录或 AstrBot 双机器人配置作为日常运行态。

## Git 工作流

- 根仓和五个子仓分别检查状态、提交和维护历史；不要从根仓暂存 submodule 内普通文件。
- 框架 fork 本地使用 `deployment` 分支，`origin` 指向 `MengLeiFudge` fork，`upstream` 指向官方仓库。MaiBot 实例共享 origin，夜凛、星遥、月澄推送目标分别为 `deployment-yelin`、`deployment-xingyao`、`deployment-yuecheng`，蓝铃为 `deployment`；获准推送时使用明确 refspec，禁止用一个账号的历史覆盖另一个账号。
- 框架提交完成后，根仓只记录新的 gitlink。
- 本次任务完成且必要检查通过后，自动提交本次范围内的改动；不要等待用户再次要求提交。子项目提交完成后，同步提交根仓的 gitlink 更新。用户明确要求暂不提交时除外。
- 未经用户明确批准不得 push，也不得把无关 dirty change 带入提交。

## 验证

遵守会话级验证边界。默认只做精确 diff/配置重读、适用的 Python 编译、PowerShell parser、项目 build 和 LSP；不启动机器人、NapCat、浏览器或网络探针，不运行测试、lint 或 format。环境缺少适用 parser/LSP 时如实记录，不能用运行时启动替代。供 Windows PowerShell 5.1 执行且包含中文的 `.ps1` 必须保存为带 BOM 的 UTF-8；修改后同时核对 BOM 和 parser，避免无 BOM 文件在本机编码下把注释后的代码吞入注释。

用户已授权上述变更后的自动重启；此类生效操作允许执行既有启动入口的必要就绪检查，以确认服务和 OneBot 连接恢复。该授权不扩展到发送聊天、调用模型、浏览器验证或其它测试。
