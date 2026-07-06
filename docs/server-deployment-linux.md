# Linux / 1Panel 部署双棉花糖

结论：1Panel 可以用来安装和托管 AstrBot Core，但它只解决 AstrBot 管理端本身；本仓库的双棉花糖还需要同步本地插件、两路 aiocqhttp 平台配置、两个 NapCat 协议端和运行态数据。

官方部署边界：

- AstrBot 1Panel 文档：https://docs.astrbot.app/deploy/astrbot/1panel.html
- AstrBot Docker 文档：https://docs.astrbot.app/deploy/astrbot/docker.html
- AstrBot aiocqhttp / OneBot 文档：https://docs.astrbot.app/platform/aiocqhttp.html

## 推荐拓扑

```text
服务器
├── 1Panel / Docker
│   └── AstrBot Core
│       ├── WebUI: 6185
│       ├── aiocqhttp angel: 6200/ws
│       ├── aiocqhttp demon: 6201/ws
│       └── data/plugins/  # 从本仓库 plugins 同步
├── NapCat angel 1443944862 -> ws://127.0.0.1:6200/ws
├── NapCat demon 2629227874 -> ws://127.0.0.1:6201/ws
└── qqbot 仓库工作副本
    ├── astrbot/  # 官方源码 submodule，仅作参考
    ├── plugins/
    ├── config/astrbot/
    └── tools/maintenance-scripts/
```

官方 1Panel 安装后的容器数据目录应持久化。若使用官方 Docker 路径，重点是把 AstrBot 的 `/AstrBot/data` 挂载出来，后续插件、配置和运行态都落在这个持久化数据目录下。

## 必须迁移的仓库内容

- `plugins/astrbot_plugin_qqbot_features`
- `plugins/astrbot_plugin_topic_concentration`
- `plugins/astrbot_plugin_local_artifact_api`
- `config/astrbot/` 里的脱敏配置示例，用作服务器 WebUI / 数据库配置参考
- 必要的运行态数据：表情包、游戏存档、RightCodes 积分、Lolicon 元数据和 artifact 发布状态

不要迁移或提交：

- LLM provider key、OneBot token、QQ 登录态、cookies、数据库密钥
- 私聊记录、运行日志、临时缓存
- 本机 Windows 启动脚本作为服务器运行入口

## 部署步骤

1. 在 1Panel 安装 AstrBot，确认 WebUI 端口 6185 可访问。
2. 在 AstrBot 数据目录中放入本仓库三个本地插件，保持目录名不变。
3. 在 AstrBot WebUI 中配置两个 aiocqhttp 平台：
   - 天使：`ws://127.0.0.1:6200/ws`
   - 恶魔：`ws://127.0.0.1:6201/ws`
4. 在服务器安装并启动两个 NapCat 实例，分别登录 `1443944862` 和 `2629227874`，反连对应端口。
5. 在 AstrBot WebUI 中恢复两个人格和插件运行态配置；密钥只填服务器运行态，不写回仓库。
6. 迁移必要的 `plugin_data` 运行态目录。Windows 路径要改成 Linux 路径，尤其是源码知识根、表情图片根和导出目录。
7. 重启 AstrBot 和两个 NapCat，检查：
   - WebUI 6185 ready
   - OneBot 6200 / 6201 已建立反连
   - 插件列表包含三个本地插件
   - 两个 QQ 账号都能各自私聊触发普通 LLM
   - 群聊固定命令只执行一次

## 后续修改路线

推荐唯一主线：本机改动 -> 本机验证 -> Git 提交 -> 服务器 `git pull` -> 同步插件到 AstrBot 数据目录 -> 重启 AstrBot / NapCat。

原因：

- 本机仓库已经有完整测试、启动脚本、历史 draft 和提交规则。
- 服务器应保持运行态干净，减少临时调试文件、密钥和登录态被误提交的风险。
- 所有改动先进入 Git，服务器只部署可追溯版本，回滚也更明确。

服务器上直接用 Codex 改只作为紧急热修：修完必须把 diff 拉回本机，复核后提交，并让服务器回到 Git 跟踪版本。不要让服务器成为第二个长期开发源。

## 成本控制口径

截图里的主要支出来自 `deepseek-v4-flash`，2026-07-03 单日约 151 次请求、9,130,552 tokens，平均每次请求约 60k tokens。降低请求次数只能解决一部分，更关键的是压缩每次 LLM 请求前注入的公开上下文、源码知识和主动接话批量窗口。

当前低成本默认：

- 公开群上下文：最多 8 条、1200 字。
- 源码知识：最多 4 条、2600 字，单域 Python fallback 扫描 80 个文件，单文件 220000 字节。
- 主动接话批量判定：窗口 480 秒、触发上限 50 条，送入模型的有效消息最多 40 条；主动历史注入最多 24 条、2400 字。

复杂技术追查需要更完整证据时，再临时调高这些运行态配置；不要把大 prompt 档作为日常默认值。
