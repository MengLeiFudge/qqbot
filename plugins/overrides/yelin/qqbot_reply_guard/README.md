# QQBot 连发与引用

`qqbot_reply_guard` 为夜凛主人私聊从接收时起收集两秒内的连续消息，并为 Planner 和原生 Replyer 展开本轮同会话的普通引用原文。准备上下文已经花掉的时间计入两秒窗口，新消息仍交给原有中断流程重新收集。

插件不再追加回复决策、搜索和记忆规则，也不在生成后调用另一个模型核对执行动作。阶段回复与历史查阅指导放在原生 `[chat.reply_style]` 配置中；联网能力由现有搜索插件提供。Planner 决策后调用原生 `reply`，原生 Replyer 结合完整人设、上下文和工具证据生成正文，再经过原有后处理分段与发送。

回复分段和发送见 [QQBot 回复分段、等待与引用](../../../maibot/qqbot_reply_timing/README.md#分段)。

将 `config.example.toml` 复制为本机 `config.toml` 后启用。连发与引用功能核对目标机器人 QQ、身份插件配置中的主人和真实私聊。
