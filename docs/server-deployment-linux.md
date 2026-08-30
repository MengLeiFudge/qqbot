# Linux / 1Panel 部署边界

本工作区的事实拓扑是两个独立框架项目加一个共享 NapCat 接入层，不再是单个 AstrBot Core 承载两个账号。

## 组件拓扑

```text
qqbot superproject
├── astrbot/          云栖 1443944862，WebUI 6185，OneBot 6200，artifact API 8080
├── maibot-yelin/     夜凛 2629227874，WebUI 8003，连接 NapCat 6201
└── napcat/           四账号 QQ/OneBot 接入；星遥和月澄当前没有 Bot Core
```

AstrBot 与 MaiBot 必须使用各自 fork 的 `deployment` 分支和该分支固定的稳定 Release。1Panel 或 Docker 只负责托管具体组件，不能替代 fork 中的本地插件、chat-only 策略或账号配置。

## 持久化边界

云栖 AstrBot 需要持久化 `astrbot/data/`，其中包括实际 Core 配置、本地插件配置、数据库、插件数据和日志。插件源码由 AstrBot fork 自身的 `data/plugins/` 提供，不从 qqbot 根目录同步。

夜凛 MaiBot 需要持久化 `maibot-yelin/config/`、`data/`、`logs/` 和插件实际 `config.toml`。不得恢复已归档的云栖 MaiBot 数据；夜凛使用自己的全新记忆。启动 Core 前必须执行 `scripts/enforce_chat_only.py`，确保第三方插件只有 `napcat_adapter` 可启用。

NapCat 的程序包、QQ 登录态、实际 OneBot 配置和日志位于 `napcat/onekey/`、`napcat/data/`。这些内容不随 Git 分发，应通过受控备份恢复或在目标主机重新登录。部署平台必须确认所选 NapCat/QQ 运行方式受该系统支持；Windows 根 PowerShell 启动器不能直接作为 Linux service 入口。

## 部署步骤

1. 使用 `git clone --recurse-submodules` 获取 qqbot，并确认两个 submodule 都位于采用版本。
2. 分别为 AstrBot 和 MaiBot 恢复本机运行配置，只在运行环境填写 provider key、OneBot token 和其他密钥。
3. 为云栖配置 NapCat reverse WebSocket client `ws://127.0.0.1:6200/ws`。
4. 为夜凛配置 NapCat forward WebSocket server `127.0.0.1:6201`，MaiBot `napcat_adapter` 使用同一端口和 `connection_id=yelin`。
5. 分别使用项目自己的依赖环境和启动入口建立服务；不要从 qqbot 根目录复制框架插件或配置。
6. 将 AstrBot `6185/6200/8080`、MaiBot `8003` 和 NapCat `6201` 的监听/连接状态纳入平台健康检查。

星遥 `3056830689:6202` 与月澄 `3109326090:6203` 当前只保留 NapCat 配置，不部署 AstrBot 或 MaiBot，也不加入默认服务启动组。

## 更新与发布

更新必须显式执行：先在对应 fork 的 `deployment` 分支合入官方最新稳定 Release，处理本地兼容并提交，再更新 qqbot 的 submodule 指针。启动服务时不得自动追踪 upstream 或自动升级。

三个仓库分别发布：

1. `MengLeiFudge/AstrBot` 的 deployment 提交。
2. `MengLeiFudge/MaiBot` 的 deployment 提交。
3. `MengLeiFudge/qqbot` 的 NapCat/编排变更和两个新 gitlink。

真实 token、QQ 登录态、cookies、数据库、日志、会话记录和运行配置不得进入 Git 或部署日志。服务器热修必须回流到对应 fork；不要让服务器副本形成新的源码事实源。
