# QQBot

基于 `NoneBot2 + OneBot V11 + NapCat` 的 Python QQ 机器人项目。

这个仓库承接旧 `mirai` 机器人的功能迁移，并在 Python 侧补充插件注册、AI 接入、本机管理端和 NapCat 一键启动流程。

开发流程、测试分层、AI/Codex 边界和重启验证规则见 `AGENTS.md`。

## 当前能力

- `NapCat -> OneBot V11 -> NoneBot2` 反向 WebSocket 链路
- 本机管理端：状态查看、重启、全局插件开关、管理员管理、启动日志查看
- 基础管理：菜单、帮助、管理员维护
- 群管助手：连续相同消息复读一次、群管、自动同意管理员邀请入群、戳一戳响应
- 群功能：捐献、Lolicon 美图
- 游戏/工具插件：异形工厂、Factorio 下载链接、养鲲、Arc、落樱之都
- 社交事件：自动同意好友申请、自动同意邀请入群、戳一戳响应
- AI 接入：OpenAI-compatible 多 provider 配置、流式响应、群上下文、全群保守主动介入、显式求助复杂问题占位回复、领域知识候选、连续短回复、个人回复风格、RightCodes 生图、需求提案、Codex 会话中转

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
QQBOT_AI_KEY_OPENROUTER=你的 OpenAI-compatible API Key
QQBOT_AI_KEY_RIGHTCODES=你的 RightCodes API Key
FACTORIO_USERNAME=你的 Factorio 用户名
FACTORIO_TOKEN=你的 Factorio 官网 token
```

AI provider 示例：

```toml
[ai]
enabled = true
default_profile = "openrouter"
max_context_messages = 12
group_context_messages = 30
show_metrics = false
bot_name = "QQBot"

[ai.providers.openrouter]
enabled = true
provider = "openai_compatible"
base_url = "https://example.com/v1"
model = "gpt-5.4-mini"
api_key_env = "QQBOT_AI_KEY_OPENROUTER"
timeout_seconds = 45
max_output_tokens = 4096
```

群聊普通 AI 对话不需要每群开关；所有群都会使用保守主动触发判定，只有明确求助、提到机器人、领域问题或上下文适合介入时才进入 AI 回复。普通非 @ 主动介入会先按群缓冲一小段会话，再统一判断是否回复；@ 机器人、点名机器人和生图命令仍会即时处理。主动介入可以回复最近一段群聊整体，并按场景决定是否引用最关键的触发消息。复杂问题、数学/推理问题和强领域关联问题会优先保证准确性，但不会先发“我先看看”这类占位消息；如果等待期间群友已经给出一致答案，机器人会引用该答案并短确认，避免重复刷屏。

领域群会优先按对应项目资料和源码回答：`319567534` 对应 MLJ_DSPmods / 万物分馏，`1035445959` 对应 OrbitalRing-MOD / 星环。相关机制、配方、功率、建筑或代码问题不会用通用游戏经验直接回答。

长期知识分为可信知识和候选知识。管理端“长期记忆”页可以触发知识候选扫描、查看待处理 AI 任务，并维护可信事实；候选知识不会因为普通群聊一句话直接变成可信事实。

小米 MiMo 对话和 TTS 已停用。语音回复模式暂时降级为文字回复；后续接入新的 TTS provider 前，不会再调用小米转语音。

## 启动

日常启动：

```powershell
Set-Location D:\project\qqbot
.\scripts\start_all.bat
```

`start_all.bat` 会启动 qqbot 和 NapCat，并等待 OneBot 连接成功。启动日志写入 `logs/start_all/<timestamp>/`。

单独启动 qqbot：

```powershell
Set-Location D:\project\qqbot
.\scripts\start_bot.ps1
```

单独启动 NapCat：

```bat
cd /d D:\project\qqbot
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
- `支持` / `捐献` / `/donate`
- `群禁言` / `群解禁` / `禁30@某人` / `解禁@某人` / `踢出@某人`
- `开群色图` / `关群色图` / `开图片显示` / `关图片显示`
- `来点色图` / `美图 凯露 10`
- `arctj10.5` / `zm` / `开*` / `10骨折光` / `猜 骨折光` / `arcqh` / `jx` / `archd` / `xz`
- `Factorio下载链接` / `异星下载链接`：获取 Factorio: Space Age Windows 安装包临时链接
- `i CrRgSbWy` / `view CrRgSbWy` / `chart CrRgSbWy`
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
