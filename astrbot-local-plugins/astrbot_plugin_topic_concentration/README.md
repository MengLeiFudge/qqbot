# 棉花糖主动接话门控

作者：MengLei

## 插件用途

本插件控制 AstrBot 普通群聊主动接话是否放行，并负责天使/恶魔双平台下普通 LLM worker 调度。

它不直接发送最终回复，也不自己选择模型。provider、模型切换和回退链只使用 AstrBot 当前会话配置。

## 核心行为

- 主动接话只处理普通群聊窗口；明确 @、引用当前 bot 和私聊只进入 worker 调度，不进入主动接话判定。
- 保留 AstrBot Core 的主动回复开关、白名单和 method 门槛。
- 过滤另一个棉花糖发出的普通消息，避免双 bot 互相触发。
- 插件只做机械门控、重复事件去重、同群 in-flight、群冷却、话题冷却、worker claim、上下文裁剪和接话意愿信号；是否应该接话由 LLM 基于群聊语境判断。
- 需要 LLM 判定时，会把 AstrBot 原生群聊上下文节选、引用原文、最近窗口和插件信号一起交给当前会话 provider；普通主动接话判定失败则静默跳过。
- 明确出现“棉花糖”“棉花糖在吗”“呼叫棉花糖”等命名呼叫时，插件本地直接放行当前选中的普通 LLM worker；同一用户短时间内紧接“在吗”等探活短句也继承这次呼叫，不依赖主动接话判定 provider。
- 同一群已有主动接话判定正在等待 LLM 时，新的普通主动接话候选直接跳过；明确 @ 和私聊不受影响。
- 固定命令、生图、菜单、群务、下载、游戏存档等有副作用入口不参与 worker 负载均衡，交给 `astrbot_plugin_qqbot_features` 的固定命令 claim 处理。
- 普通 LLM 请求按两个 worker 调度：目标 bot 空闲时由目标处理；目标 bot 正在等待 LLM 返回时，可由另一个 bot 用自己的身份代班/接力。

## 事件入口

本插件通过启动时 patch AstrBot 的 `GroupChatContext.need_active_reply` 接入主动接话判断；同时用高优先级事件 handler 和 LLM request/response hook 管理普通 LLM worker busy/lease，因此管理端不会显示普通群聊命令。

## 双 bot 边界

- 天使和恶魔同群时，同一真人消息会被两个平台各收到一次。
- 本插件按 `group:<群号>` 共享窗口和冷却，避免同一消息双路判定。
- 本插件按 `group:<群号>` 共享 in-flight 门控，避免上游慢或超时时多个旧主动回复结果一起返回刷屏。
- 同一条普通 LLM 消息按 canonical claim 只选择一个 worker。claim key 优先使用群号、发言者、当前纯文本、@ 目标、引用消息和时间桶，不依赖双平台可能不一致的 message_id。
- worker busy 状态在 LLM request 时标记，在 LLM response 时释放，并有内存 lease 兜底，避免上游慢回复期间继续把新普通 LLM 请求压给同一个 bot。
- 另一个 bot 的普通输出不会触发当前 bot 主动接话。
- 明确 @ 当前 bot 或私聊仍走 AstrBot 直接请求链路，但进入该链路前会先经过本插件 worker 调度。

## 数据与安全边界

- 只维护内存窗口、冷却和短期兴趣状态。
- 不读写用户资产、积分、游戏存档或私聊内容。
- 不实现独立 provider 顺序、独立 fallback 或判定专用模型。
