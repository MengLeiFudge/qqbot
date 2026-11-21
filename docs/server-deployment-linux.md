# Linux / 1Panel 部署

1. 克隆 `qqbot`，按 [部署清单](../deployment/frameworks.json) 获取官方框架归档。为每个启用账号准备独立目录与依赖环境。
2. 恢复各实例配置和运行数据。云栖挂载 `astrbot/data/`，MaiBot 分别挂载各自的 `config/`、`data/`、`logs/` 和本机插件配置。
3. 在运行目录就位后，用 `python3 scripts/frameworks/deploy_plugins.py <Target>` 安装自研插件。启动 MaiBot 前在相应运行目录运行蓝铃配置校验或风铃、夜凛的聊天插件策略。[框架与插件部署](framework-deployment.md)
4. 按 [账号清单](../napcat/accounts.json) 配置 NapCat。云栖使用反向 WebSocket，MaiBot 实例使用各自对应的正向 WebSocket。夜凛保持停用。
5. 使用服务管理器启动框架和协议端，按 [聊天实例](chat-instances.md) 验证 WebUI、OneBot 和各本机服务的监听与连接。选择部署平台支持的 NapCat/QQ 运行方式。

DSP 向量库随 AstrBot 的数据目录持久化。为 AstrBot 插件配置本机实际的 `source_root`，MaiBot 使用同机 `127.0.0.1:8081` 做只读检索。NapCat 登录态和实际 OneBot 配置独立备份。

更新从部署清单读取固定版本，准备完官方包后显式更换。保留每个实例的配置和数据，并单独部署自研插件。服务端插件改动回流到 `qqbot/plugins/`。
