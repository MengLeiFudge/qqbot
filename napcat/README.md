# NapCat 账号项目

本目录由 qqbot 根仓库管理，负责账号清单中各 QQ 账号的 NapCat/OneBot 接入，不属于 AstrBot 或 MaiBot。

## 可提交内容

- `accounts.json`：账号名称、QQ、固定 OneBot 端口、连接方向和当前框架归属。
- `scripts/configure-account.ps1`：把账号清单落实到本机 OneBot 配置，并部署本地社交请求插件。
- `scripts/ensure-account.ps1`：按账号确保配置、内置插件、进程和端口 ready。
- `scripts/hide-account-windows.ps1`：连接完成后只隐藏精确账号进程树拥有的窗口。
- `scripts/start-account.ps1`：兼容 NapCat OneKey 启动器的底层单账号入口。
- `scripts/ensure-builtin-plugin.ps1`：校验或恢复官方内置插件。
- `scripts/ensure-social-plugin.ps1`：部署并启用 `plugins/napcat-plugin-qqbot-social/`，从账号清单生成仅使用 NapCat 的账号集合。
- `scripts/update.ps1`：显式更新 NapCat 最新稳定 Release，并迁移账号配置。

## 本机运行态

`onekey/` 和 `data/` 被根 `.gitignore` 排除：

- `onekey/` 保存 NapCat 程序包、QQ 登录态、缓存和 `onebot11_<QQ>.json` 实际配置。
- `data/` 保存账号日志、快速登录标记、下载、归档和更新状态。

这些目录可能包含 token、登录态和日志，不得强制加入 Git。更新器替换 OneKey 包后会迁移已有账号配置，并重新按 `accounts.json` 校正连接方向和端口。

使用 `onekey/napcat/` 的 Shell 部署时，`start-account.ps1` 调用官方 `launcher-user.bat`，由系统注册表解析 QQ 程序位置。账号进程分开运行，不代表 QQ 程序安装独立；桌面 QQ 的热更新也会影响下一次 NapCat 启动。恢复前读取该 QQ 安装的 `versions/config.json` 中 `curVersion`，并核对实际 NapCat Release 的 `packages/napcat-core/external/napi2native.json` 支持表中的完整构建和架构。QQ 数字签名有效只证明文件签名通过，不能证明该构建可被 NapCat 注入或支持协议 Hook。

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
