# NapCat 账号项目

本目录由 qqbot 根仓库管理，负责账号清单中各 QQ 账号的 NapCat/OneBot 接入，不属于 AstrBot 或 MaiBot。

## 可提交内容

- `accounts.json`：账号名称、QQ、固定 OneBot 端口、连接方向和当前框架归属。
- `scripts/configure-account.ps1`：把账号清单落实到本机 OneBot 配置，并部署本地社交请求插件。
- `scripts/ensure-account.ps1`：按账号确保配置、内置插件、进程和端口 ready。
- `scripts/hide-account-windows.ps1`：连接完成后只隐藏精确账号进程树拥有的窗口。
- `scripts/start-account.ps1`：读取项目内选版清单，通过官方 NapCat 引导程序启动独立 QQ。
- `scripts/ensure-builtin-plugin.ps1`：校验或恢复官方内置插件。
- `scripts/ensure-social-plugin.ps1`：部署并启用 `plugins/napcat-plugin-qqbot-social/`，从账号清单生成仅使用 NapCat 的账号集合。
- `scripts/update.ps1`：更新 NapCat 最新稳定 Release，再选择该 Release 支持的最新 Windows x64 QQ 完整构建。
- `scripts/qq-runtime.ps1`、`scripts/update-qq.ps1`、`scripts/update-runtime.ps1`：共用的选版读取、QQ 安装包准备与更新事务支持。
- `scripts/register-auto-update.ps1`：维护现有自动更新计划，默认每小时和用户登录两分钟后检查一次。

## 本机运行态

`onekey/` 和 `data/` 被根 `.gitignore` 排除：

- `onekey/` 保存 NapCat 程序包、QQ 登录态、缓存和 `onebot11_<QQ>.json` 实际配置。
- `data/` 保存账号日志、快速登录标记、下载、归档和更新状态。

这些目录可能包含 token、登录态和日志，不得强制加入 Git。更新器替换 OneKey 包后会迁移已有账号配置，并重新按 `accounts.json` 校正连接方向和端口。

机器人使用 `onekey/napcat/` 和 `onekey/qq/<完整构建>-x64/` 中的官方程序包；`onekey/qq-runtime.json` 记录当前配对版本。`start-account.ps1` 只读取该清单，不再通过注册表查找桌面 QQ。桌面 QQ 的安装和自动升级与机器人选版分开。各账号仍使用原有登录态和独立进程，不复制其他账号的聊天数据。

启动前核对 QQ 的 `versions/config.json`、包内 `package.json` 和清单中的完整构建、架构、NapCat 版本；账号运行期间保持 QQ 选版文件的共享只读句柄，阻止内置热更新替换该文件。版本漂移或首次尚未准备独立 QQ 时停止启动，并提示执行配对更新。QQ 数字签名有效只证明文件签名通过，不能证明该构建支持 NapCat 协议 Hook。

## NapCat 与独立 QQ 更新

根 `scripts/update-all.ps1` 和自动计划均调用同一个 `napcat/scripts/update.ps1`。更新器查询 NapCat 最新稳定 Release，读取该 Release 的 `packages/napcat-core/external/napi2native.json`，按完整版本排序选择其中最高的 Windows x64 QQ 构建。NapCat 已是最新时仍检查独立 QQ，不再直接跳过。

先下载并核验两个安装包，再停止本项目所属账号进程，按 NapCat → 独立 QQ 选择的顺序激活。NapCat 归档校验官方 Release 的大小和 SHA-256；QQ 使用官网元数据与公开下载签名接口，校验腾讯数字签名、安装包完整版本和解包后构建，仅解包，不执行系统安装器或修改桌面 QQ 注册表。解包器取自同一官方 OneKey Release 并核验归档。旧程序包、账号配置、插件和登录数据保留。

官网最新 QQ 可能领先 NapCat 的支持表。此时不能把同一 `9.9.x` 系列当作兼容证据：缓存或官网无法提供目标完整构建时，在停止机器人之前报错，保留当前组合。可以把未修改且带有效腾讯签名的目标 Windows x64 完整安装包放入 `napcat/data/downloads/`（文件名以 `QQ` 开头、扩展名 `.exe`），更新器会核对包内版本后复用；不会降级为另一旧构建或借用桌面 QQ。

手动更新：

```powershell
.\napcat\scripts\update.ps1 -AssumeYes
```

激活失败时先恢复 NapCat 和 QQ 选择，再按需恢复原有机器人；激活成功且需要生效时复用根入口重启云栖、夜凛和蓝铃，保留健康 NapCat 登录态，并检查 ready、OneBot 连接及本轮原生协议 Hook 日志。一次启动失败后记录状态和日志，不反复重启。自动更新遇到激活中断或失败，会暂停该 Release 的再次自动激活，需先核对 `data/updates/napcat.json` 与 `data/logs/updates/`，修复后手动运行更新入口。

注册或移除计划：

```powershell
.\napcat\scripts\register-auto-update.ps1
.\napcat\scripts\register-auto-update.ps1 -Remove
```

计划沿用 `QQBot-NapCat-AutoUpdate`，以当前登录用户的交互会话运行，不保存密码。首次注册立即检查；常规检查无更新或包准备失败时不重启机器人。

## 自动同意请求

所有账号自动同意好友申请、邀请机器人入群和成员加群申请。云栖由 AstrBot 的 `astrbot_plugin_qqbot_features` 处理；夜凛、蓝铃由各自 MaiBot 的 `napcat_adapter` 接入层处理；账号清单中未绑定框架的账号由 `napcat-plugin-qqbot-social` 处理，避免重复执行。

`configure-account.ps1` 会把本地插件复制到实际 NapCat 插件目录并启用；账号启动和更新入口均调用该配置步骤。仅使用 NapCat 的账号在下一次启动时加载该插件；现有进程需要重新加载插件或重启对应 NapCat。申请处理不发送聊天消息，失败写入各自运行日志。

## 固定端口

- 云栖 `1443944862`：reverse client -> `ws://127.0.0.1:6200/ws`
- 夜凛 `2629227874`：forward server `127.0.0.1:6201`
- 星遥 `3056830689`：forward server `127.0.0.1:6202`
- 月澄 `3109326090`：forward server `127.0.0.1:6203`
- 蓝铃 `3600812036`：forward server `127.0.0.1:6204`

根 `all/yunqi/yelin/lanling` 入口自动管理云栖、夜凛和蓝铃。单独维护星遥或月澄时可在 Windows PowerShell 中运行：

```powershell
.\scripts\ensure-account.ps1 -Target xingyao
.\scripts\ensure-account.ps1 -Target yuecheng
```

首次登录可能需要二维码。再次启动时，`ensure-account.ps1` 先读取当前账号运行日志；检测到 QQ 离线或明确的 `Process exited.` 时，只重建该账号一次，重新进入登录流程。官方启动器可能在 QQ 退出后停在 `pause`，因此启动器进程仍存在不能证明 QQ 可用；新实例再次退出或离线时明确报错，不继续重启。健康账号继续复用。多个账号需要新启动时，共用登录锁逐个等待登录完成，避免覆盖同一个二维码图片；已在线账号的复用仍可并行。OneBot 端口存在不能覆盖日志中明确的离线或待扫码状态。根账号启动窗口会等待扫码、登录和 OneBot 连接完成，再调用 `hide-account-windows.ps1` 隐藏该账号 `start-account.ps1` 进程树拥有的 QQ/NapCat 窗口；脚本不会按窗口标题、进程名或 QQ 号扫描其他进程。失败或超时时不收窗。快速登录成功标记位于 `data/quick-login/<QQ>.ready`；标记和实际登录态均只属于本机。

需要手动重新打开蓝铃登录窗口时，在 `D:\project\qqbot` 的 PowerShell 中运行：

```powershell
.\napcat\scripts\ensure-account.ps1 -Target lanling -ForceRestart -UseChildWindow
```

使用蓝铃账号的手机 QQ 扫描窗口里的二维码并确认登录。窗口也会打印当前二维码图片路径，二维码刷新后需重新打开图片。这个命令只重启蓝铃的 NapCat，不清除登录数据。正常使用仍运行根 `scripts\start-all.bat`，等待扫码期间不要重复启动。
