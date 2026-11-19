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

- 根 `qqbot`：维护 `astrbot`、`maibot-yelin`、`maibot-lanling`、`maibot-fengling` 四个 gitlink，维护 `napcat/`、`napcat/accounts.json`、根 `scripts/` 和跨项目文档。
- `astrbot/`：独立的 `MengLeiFudge/AstrBot` fork 工作树，维护云栖本地插件、配置示例、项目脚本和项目内运行态。
- `maibot-yelin/`：夜凛独立工作树，暂时停用并保留配置与数据。
- `maibot-fengling/`：风铃（QQ `3056830689`）的 MaiBot 工作树，技术 Target 为 `fengling`，角色数据从空白开始。
- `maibot-lanling/`：蓝铃独立 MaiBot 工作树；与风铃、夜凛对齐通用插件，伴侣关系和专属模块独立维护。
- `napcat/`：现行四个 QQ 账号共享的协议端项目；程序包和实际账号配置保留在本机，非敏感账号映射与维护脚本由根仓跟踪。

根目录不得重新建立框架级 `config/`、`plugins/`、`data/`、虚拟环境或框架内部启动逻辑。根脚本只能读取账号清单、调用子项目入口和汇总 ready 状态。

## 固定账号合同

- 云栖 `1443944862`：AstrBot，OneBot `6201`，负责聊天和全部固定功能。
- 夜凛 `2629227874`：MaiBot，OneBot `6202`，暂时关闭，`autoStart=false`。
- 风铃 `3056830689`：MaiBot，OneBot `6204`，技术 Target 为 `fengling`。
- `3109326090` 已注销，不在账号清单内；其历史工作树已归档，不保留 gitlink、端口或启动参数。
- 蓝铃 `3600812036`：MaiBot，OneBot `6203`，负责聊天、拍一拍和只读知识问答。

根日常启动 Target 为 `all`、`yunqi`、`yelin`、`lanling`、`fengling`；`all` 只启动清单中 `autoStart=true` 的账号。`3109326090` 已从账号清单和脚本参数中移除，传入旧 Target 必须直接失败，不得回退启动旧实例。

## AstrBot 边界

- AstrBot 只绑定云栖，不得恢复 `both/angel/demon` profile、夜凛平台、双 worker、跨账号 command claim、忙闲代班或可选择 command owner。
- 在棉花糖家族内，云栖是所有现有固定命令、数据写入、群务和副作用功能的唯一运行 owner。
- 本地插件源码放在 `astrbot/data/plugins/` 的原生位置；真实插件配置、数据库、日志、缓存和 `plugin_data` 不跟踪。
- 行为调整必须遵守“框架核心边界”，通过现有配置和本地插件 API 实现，禁止直接修改 AstrBot Core。模型 API 路由维护先读 `docs/model-routing.md`。
- AstrBot 自己的 `scripts/start.ps1` 和 `scripts/update.ps1` 必须可从项目目录独立使用，不依赖根文件。

## MaiBot 边界

- 夜凛、蓝铃、风铃使用独立工作目录，WebUI 分别为 `8002/8003/8004`，消息服务分别为 `8022/8023/8024`；数据库、记忆、虚拟环境和个人工作区独立。角色与配置维护先读 `docs/bot-roles.md`、`docs/chat-instances.md`。
- 夜凛、蓝铃、风铃的适配器分别连接 `6202/6203/6204`，技术 connection_id 为 `yelin/lanling/fengling`。基础插件为 `napcat_adapter`、`cpa_session`、`qqbot_poke`、`qqbot_knowledge`、`qqbot_identity`、`qqbot_visual`、`qqbot_web_search`、`qqbot_reply_timing`；共同扩展为 `org_orge-8_better-diary`、`qqbot_diary`、`qqbot_workspace`、`qqbot_proactive`、`qqbot_reply_guard`。
- `qqbot_knowledge` 只通过 `127.0.0.1:8081` 使用云栖持有的 DSP 向量检索结果，不在 MaiBot 侧建立额外 DSP 索引；云栖不可用时退回无 DSP 证据的普通聊天。
- 夜凛和风铃仅启用上述通用插件，其余业务插件禁用；蓝铃原有伴侣专属模块独立保留，不复制给夜凛或风铃。
- 夜凛、风铃启动前执行 `scripts/enforce_chat_only.py`，允许列表必须包含共同扩展；解析失败或无法确认禁用时停止启动。蓝铃沿用 `scripts/validate_plugin_config.py`，不得自动改写其专属插件启用选择。
- 三台 MaiBot 的 QQ 内插件管理入口保持禁用。工作区只向身份核验后的主人私聊开放；首次没有既有私聊时，等待真实主人消息绑定，再由公开重载接口注册 Host 会话限制。
- MaiBot 自己的 `scripts/start.ps1` 和 `scripts/update.ps1` 必须可从项目目录独立使用，不依赖根文件。
- 所有框架的首条公开答复等待、后续分段速度及阶段研究遵守 `docs/model-routing.md` 的“回复耗时排查”合同；只在本地聊天插件中实现。

## 跨框架功能维护

现行角色以 `docs/bot-roles.md` 为准。MaiBot 通用插件在各自原生 `plugins/` 维护，不建立根共享源码副本或同步脚本；相似功能分别保留角色身份、会话绑定、工作区和数据边界。云栖继续持有固定业务命令及其共享数据；个人日记、笔记和主动联系归各 MaiBot 自己维护，不复制其他账号运行数据。跨框架只读知识继续由云栖唯一 DSP 物理库提供，MaiBot 调用 localhost 检索接口。

## NapCat 边界

- `napcat/accounts.json` 是账号、QQ、固定端口、连接方向和当前框架归属的非敏感真源。
- `napcat/scripts/configure-account.ps1` 将清单落实到本机 `onebot11_<QQ>.json`；不得在其他脚本复制账号端口常量。
- 云栖使用 reverse WebSocket client 连接 AstrBot `ws://127.0.0.1:6201/ws`。
- 夜凛、蓝铃、风铃分别提供 forward WebSocket server `6202/6203/6204`；注销账号不再启动 NapCat。
- 各账号 NapCat 面板端口为 `6101/6102/6103/6104`，由 `accounts.json` 的 `napcatWebuiPort` 在启动前写入共享 `webui.json`，不再手工改面板端口。
- `napcat/onekey/`、`napcat/data/`、QQ 登录态、token、缓存和日志不进 Git。
- NapCat 启动和更新只由 `napcat/scripts/` 负责；根脚本不得实现包替换或账号进程细节。维护前读取 `napcat/README.md` 的独立 QQ 与配对更新说明。
- 机器人使用项目内独立 QQ，禁止回退桌面 QQ。桌面 QQ 是主人自用账号，与机器人账号无关，不得据此推断顶号，也不要求主人退出。更新只由人工触发，先选择 NapCat 最新稳定 Release，再在其支持表内按版本从新到旧选择能够取得、校验并准备成功的 Windows x64 完整 QQ 构建；来源包括已有独立运行包、本地缓存、QQ 官网和官方 OneKey 包提供的下载地址。较新候选不可用时继续选择下一项，包准备成功后按 NapCat→QQ 顺序激活。所有兼容候选均不可用或发布元数据异常时保留原组合并报告原因。

## 启动与更新

- 根启动入口是 `scripts/start-all.bat` 或 `scripts/start-all.ps1`。
- 插件或配置改动优先热重载：云栖的 AstrBot 启动脚本已设 `ASTRBOT_RELOAD=1`，`data/plugins/` 下 `.py` 改动自动重载，提示词和配置文件改动在 WebUI 插件页手动重载；MaiBot 没有文件监听，在各自 WebUI 插件页把目标插件禁用再启用一次，runner 会重新加载该插件。QQ 内 `/pm` 插件管理入口保持禁用。只重载插件，不重启框架进程，不碰 NapCat；只有框架核心、依赖或进程级配置变化才重启框架。
- `data/cmd_config.json` 属于进程级配置：AstrBot 只在启动时读它并常驻内存，没有文件监听，手改文件后必须重启框架才生效；从 WebUI 配置页保存会同时写文件和内存并立即生效，不必重启。手改之后不要再去 WebUI 点保存，否则内存里的旧值会覆盖手改。要么“手改 + 重启”，要么全程在 WebUI 改。
- 任何重启都不重启正在运行的 NapCat：`-ForceRestart` 只停对应框架进程，NapCat 由 `napcat/scripts/ensure-account.ps1` 复用；只有用户明确要求或协议端本身异常时才重启 NapCat。
- 确认必须重启框架时复用 `scripts/start-all.ps1 -Target all -ForceRestart -SkipInstall -NoPauseOnFailure` 及其子项目入口，保留既有健康 NapCat 登录态，保持 `autoStart=false` 的夜凛关闭。记录启动截止、PID、日志和 ready/连接结果；失败或超时先确认当前状态并报告，不循环重启。
- NapCat 掉线后不得反复重试扫码：启动器只显示 1 张二维码，需要第二张就停掉该账号，并持续压住 NapCat 的自愈重启（连续 30 秒没有进程才退出），同时写入 `napcat/data/login-pause/`，15 分钟内不自动重试。账号登录必须串行：主窗口按账号清单顺序逐个打开登录窗口，前一个账号扫码完成、OneBot 就绪后才打开下一个。QQ 把连续登录请求判为异常会连带同机其他账号，遇到登录失败先停手、报告，等人到齐再扫码。
- NapCat 与独立 QQ 只做人工更新，不注册定时更新计划。换包会让所有账号重新登录，不得后台自动重试。
- 云栖顺序：AstrBot WebUI `8001`、OneBot `6201`、artifact API `8080` 和 DSP knowledge API `8081` ready，再启动云栖 NapCat并等待 established。
- MaiBot 账号先等待各自 NapCat ready，再启动对应 WebUI 并等待 adapter established；端口映射见固定账号合同。
- 启动不得自动升级框架。
- 根更新入口只调用各子项目自己的更新脚本。日常 `maibot` 更新覆盖清单中的夜凛、蓝铃、风铃；注销实例不参与。框架 fork 只合入官方最新稳定 Release，不追踪主分支每个提交，更新器不得 push。

## 安全与运行态

不得提交真实 token、API key、Authorization header、QQ 登录态、cookies、数据库、私聊或群聊记录、日志、缓存、PID、临时文件和真实运行配置。配置示例必须脱敏；无法确认字段安全时保持忽略并在文档中说明本机配置方式。

归档和清理使用根 `.codex/trash/<timestamp>/` 的可恢复路径。不要恢复旧 `maibot-yunqi/`、根框架数据目录或 AstrBot 双机器人配置作为日常运行态。

## Git 工作流

- 根仓和五个子仓分别检查状态、提交和维护历史；不要从根仓暂存 submodule 内普通文件。
- 框架 fork 的 `origin` 指向 `MengLeiFudge` fork，`upstream` 指向官方仓库。各子仓库本地分支名与 `.gitmodules` 声明一致：夜凛 `deployment-yelin`、风铃 `deployment-fengling`、蓝铃与 AstrBot 为 `deployment`，upstream 已指向同名远端分支。获准推送时仍需核对祖先关系，禁止覆盖其他账号历史。
- 框架提交完成后，根仓只记录新的 gitlink。
- 本次任务完成且必要检查通过后，自动提交本次范围内的改动；不要等待用户再次要求提交。子项目提交完成后，同步提交根仓的 gitlink 更新。用户明确要求暂不提交时除外。
- 未经用户明确批准不得 push，也不得把无关 dirty change 带入提交。

## 验证

遵守会话级验证边界。默认只做精确 diff/配置重读、适用的 Python 编译、PowerShell parser、项目 build 和 LSP；不启动机器人、NapCat、浏览器或网络探针，不运行测试、lint 或 format。环境缺少适用 parser/LSP 时如实记录，不能用运行时启动替代。供 Windows PowerShell 5.1 执行且包含中文的 `.ps1` 必须保存为带 BOM 的 UTF-8；修改后同时核对 BOM 和 parser，避免无 BOM 文件在本机编码下把注释后的代码吞入注释。

用户已授权上述变更后的自动重启；此类生效操作允许执行既有启动入口的必要就绪检查，以确认服务和 OneBot 连接恢复。该授权不扩展到发送聊天、调用模型、浏览器验证或其它测试。
