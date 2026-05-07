# QQBot

基于 `NoneBot2 + OneBot V11 + NapCat` 的 Python QQ 机器人项目。

这个仓库承接旧 `mirai` 机器人的功能迁移，并在 Python 侧补充插件注册、AI 接入、本机管理端和 NapCat 一键启动流程。

开发流程、测试分层、AI/Codex 边界和重启验证规则见 `AGENTS.md`。

## 当前能力

- `NapCat -> OneBot V11 -> NoneBot2` 反向 WebSocket 链路
- 本机管理端：状态查看、重启、全局插件开关、管理员管理、启动日志查看
- 基础管理：菜单、帮助、管理员维护
- 群管助手：随机复读、随机禁言、群管、自动同意管理员邀请入群、戳一戳响应
- 群功能：捐献、Lolicon 美图
- 游戏/工具插件：异形工厂、养鲲、Arc、落樱之都
- 社交事件：自动同意好友申请、自动同意邀请入群、戳一戳响应
- AI 接入：多 provider 配置、流式响应、群上下文、个人回复风格、需求提案、Codex 会话中转

## 目录结构

- `bot.py`：NoneBot2 启动入口
- `src/qqbot/config.py`：环境变量与运行配置
- `src/qqbot/bootstrap.py`：适配器注册、管理端路由、插件加载
- `src/qqbot/plugins/`：NoneBot matcher 与事件处理
- `src/qqbot/services/`：业务服务层、持久化、AI/Codex 编排
- `src/qqbot/services/plugin_registry.py`：插件元数据注册表
- `tests/`：长期回归测试
- `scripts/start_all.bat`：日常一键启动 qqbot 与 NapCat
- `scripts/start_bot.ps1`：单独启动 qqbot
- `scripts/start_napcat_onekey.bat`：单独启动 NapCat 一键包
- `config/qqbot.toml.example`：非敏感配置示例
- `.env.example`：敏感信息和本机账号配置示例

## 配置

配置分三层：

- `.env`：敏感信息和本机账号，例如 OneBot token、NapCat QQ、AI API key。
- `config/qqbot.toml`：机器人一般配置、路径、AI provider、默认模型等低频修改项。
- `run/settings/` 和 `run/ai/`：管理端和运行时经常变化的状态，例如全局插件开关、管理员列表、AI 对话上下文。

最小启动配置：

```text
QQBOT_CONFIG_FILE=./config/qqbot.toml
QQBOT_ONEBOT_ACCESS_TOKEN=你的 OneBot token
QQBOT_NAPCAT_QQ=你的机器人 QQ
QQBOT_AI_KEY_XIAOMI=你的 API Key
```

AI provider 示例：

```toml
[ai]
enabled = true
default_profile = "xiaomi"
max_context_messages = 12
group_context_messages = 30
show_metrics = false
bot_name = "QQBot"

[ai.providers.xiaomi]
enabled = true
provider = "xiaomi_mimo"
base_url = "https://api.xiaomimimo.com/v1"
model = "mimo-v2.5-pro"
api_key_env = "QQBOT_AI_KEY_XIAOMI"
timeout_seconds = 15
```

## 启动

日常启动：

```powershell
Set-Location D:\project\python\qqbot
.\scripts\start_all.bat
```

`start_all.bat` 会启动 qqbot 和 NapCat，并等待 OneBot 连接成功。启动日志写入 `logs/start_all/<timestamp>/`。

单独启动 qqbot：

```powershell
Set-Location D:\project\python\qqbot
.\scripts\start_bot.ps1
```

单独启动 NapCat：

```bat
cd /d D:\project\python\qqbot
scripts\start_napcat_onekey.bat
```

NapCat OneBot V11 反连地址：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

## 本机管理端

机器人启动后打开：

```text
http://127.0.0.1:8080/admin
```

管理端只面向本机访问，支持：

- 查看 qqbot / OneBot 连接状态
- 重启 Bot
- 查看和切换当前 AI 模型
- 查看和切换全局插件开关
- 查看、添加、删除 Bot 管理员
- 查看 `logs/start_all/<timestamp>/` 下的启动日志

## 常用命令入口

- `菜单` / `帮助` / `指令`
- `菜单Arc` / `菜单群管助手`：按模块名称或别名查看插件菜单
- `设置管理员 @某人` / `删除管理员 @某人`
- `设置复读2.5`
- `设置禁言概率2.5` / `设置禁言时间5 20`
- `支持` / `捐献` / `/donate`
- `群禁言` / `群解禁` / `禁30@某人` / `解禁@某人` / `踢出@某人`
- `开群色图` / `关群色图` / `开图片显示` / `关图片显示`
- `来点色图` / `美图 凯露 10`
- `arctj10.5` / `zm` / `开*` / `10骨折光` / `猜 骨折光` / `arcqh` / `jx` / `archd` / `xz`
- `i CrRgSbWy` / `p 123`
- `养鲲` / `属性` / `等级排行` / `财富排行` / `背包` / `商城` / `签到` / `boss` / `挑战`
- `注册樱花勇者` / `个人信息` / `加经验500` / `加5力量` / `恢复`

## Arc 插件

Arc 用户入口统一在 `src/qqbot/plugins/arc.py`：

- `arctj10.5`：按 PTT 推荐谱面
- `zm` / `zm5`：开始字符猜歌
- `开x` / `10曲名` / `猜 xxx`：猜歌交互
- `arcqh` / `qh`：开始或继续曲绘切片猜歌
- `jx` / `arcjx`：结束当前群内 Arc 猜歌并公布答案
- `xz` / `arcxz`：查询并下载官网最新 c 版安装包

运行状态主要落在：

- `run/data/arc/guess_sessions.json`
- `run/data/arc/guess_aliases.json`
