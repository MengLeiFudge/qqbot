# 模型 API 路由

本页约束云栖、夜凛与蓝铃的模型服务配置维护。真实凭据放在各子项目已忽略的本机配置中；修改地址时保持模型标识、任务映射、推理强度和输出限制。

| 调用 | 路由与凭据 | 配置入口 |
| --- | --- | --- |
| 聊天、规划、读图、记忆整理等文本生成 | `http://127.0.0.1:8317/v1`，CPA 客户端密钥 | AstrBot `data/cmd_config.json` 的 `provider_sources`；MaiBot `config/model_config.toml` 的生成 provider |
| 图像生成 | 同一 CPA 地址及客户端密钥 | AstrBot `astrbot_plugin_qqbot_features`；MaiBot `qqbot_draw` 本机配置，启用状态沿用账号策略 |
| MaiBot 联网搜索 | DeepSeek 官网 Responses，原有官网密钥 | 各实例 `qqbot_web_search/config.toml`；使用说明见插件 README |
| `qwen3.7-text-embedding` | 原百炼嵌入地址与凭据 | 各实例原嵌入 provider |
| `qwen3-rerank` | 原百炼重排序地址与凭据 | AstrBot 原 `bailian_rerank` provider |

嵌入与重排序仍待 CPA 支持，尚未纳入统一入口。不要仅因模型出现在 CPA 配置或 `/models` 列表，就替换这两类地址。迁移前需确认 `/embeddings`、重排序请求体与返回格式均兼容，保持向量维度和模型名称，避免损坏既有索引与记忆召回。

联网搜索单独保留官网：CPA 的 OpenAI 兼容转换链可能只保留函数工具，丢弃 Responses 原生 `web_search`。普通模型不再附加原生搜索工具；MaiBot 通过本地函数工具显式执行官网搜索。只有实际返回已完成的搜索调用和结果，才能称为联网证据。搜索配置及其密钥不随普通 provider 一起替换。

模型名称由机器人请求配置保持；CPA 内部的同名模型别名、渠道优先级与实际上游由 CPA 管理。若要求固定上游，必须另行核对 CPA 的渠道配置，不能把同名请求等同于同一个供应商。

QQ、B站、GitHub、账单管理、图片托管和 localhost DSP 共享检索属于各自业务接口，不使用 CPA 的模型地址或客户端密钥。

变更后先静态解析 JSON/TOML，逐字段确认只有获准的路由、凭据和必要搜索设置发生变化；随后按根 AGENTS 的启动入口重启并保存 ready/连接结果。服务 ready 只证明机器人完成启动，不代替真实模型与搜索调用的验收。CPA 升级后重新核对实际版本对应的路由和协议转换，不能沿用旧版支持结论。

## 费用与缓存排查

维护提示词、状态注入或模型路由时，按以下方法检查缓存与费用：

- 先确定账单日期、时区、账号凭据归属和当时的实际请求地址；配置切换前后的记录分开统计。供应商名称或模型别名不能单独证明实际上游。
- MaiBot 按 `data/MaiBot.db` 的 `llm_usage.request_type` 汇总调用次数、缓存命中/未命中输入和输出 token，分别计算三类费用。输出包含供应商计入的推理 token，不能用聊天正文长度估算。
- 缓存排查使用 `logs/maisaka_prompt/planner/<会话目录>/*.json` 中 `generation_attempts[].wire_request` 的实际输入和工具定义，比较同会话相邻请求的首个差异。Responses 的命中量取 `wire_response.usage.input_tokens_details.cached_tokens`；请求快照缺少 usage 时保留未知，不以 trace 中的零值替代。
- 保持固定系统规则和工具定义的内容、顺序稳定。分钟时间、日程、即时状态等动态信息使用公开 Hook 作为独立上下文放在稳定历史之后，并保留原有角色与优先级语义；把这些信息拼入开头的系统提示词，会截断可复用的连续前缀。历史窗口滚动和历史项重排也要单独核对。
- MaiBot 的成功调用统计不等于供应商最终账单。检查 `logs/maisaka_prompt/llm_error/` 中失败和重试的各次尝试；已有返回 usage 的截断结果可能消耗完整输出额度。核对请求与尝试标识后补算未落库用量，缺少 usage 的超时不能估作零，也不能据此声称已完全对账。
- 调整后只用获准的验证或自然产生的新请求评估命中率，记录样本数和统计时段，同时确认所需状态仍在有效输入中。跨时段聊天内容和上下文长度不同，不能把命中率变化直接换算成固定节省比例。

## 回复耗时排查

回复耗时优化以事实准确、原有人设、上下文理解和证据完整为前提，保持“生成→原有后处理分段→发送”的完整流程。MaiBot 的生成阶段使用 Planner 决策和原生 Replyer 组织正文；后处理分段由框架原有流程负责。日常生成、识图、记忆及文本辅助任务使用 `reasoning.effort = "high"`，保留原模型、上下文和输出余量；官网联网研究使用搜索插件自己的思考配置。涉及生成机制、提示词或思考强度的变化，先说明实际输入、预期收益和质量取舍，再在用户授权范围内实施。模型参数一致、调用更少或简单数字题正确都不足以证明质量等价。

所有机器人保留各自配置的发送速度。分段完成后，每轮首条公开消息的实际补等为 `max(0, 第一段原有等待 - 本轮已耗时)`；原有等待只按第一段文字计算，本轮已耗时从接收本轮消息算到第一段准备发送，不使用全文或全部分段的累计时长。第一段原等待3.6秒、已处理1秒时再等2.6秒；已处理5秒时直接发送。后续分段和研究补充按各段原有速度计算等待，不再抵扣；新表达进入新一轮后重新记录起点。失败或取消不能伪造成功，也不能重复发送结果未知的消息。

需要研究时，模型可以先发已经确认且有用的公开结论，再继续查询并补充新证据；简单聊天正常回答。MaiBot 的阶段答复同样通过原生 `reply`，`reply_reference` 只提供已确认事实和本阶段回应范围。保留必要上下文、身份和知识证据，内部推理保持隐藏。

云栖由[群聊路由插件](../astrbot/data/plugins/astrbot_plugin_topic_concentration/README.md)处理直接呼叫优先和阶段答复，由[功能合集](../astrbot/data/plugins/astrbot_plugin_qqbot_features/README.md)处理首条等待；其部署配置关闭 `buffer_intermediate_messages`。风格守卫已关闭分段的消息保持直接发送，不额外人为等待。夜凛的[原生回复规则](../maibot-yelin/plugins/qqbot_reply_guard/README.md)和蓝铃的[私聊执行检查](../maibot-lanling/plugins/qqbot_reply_guard/README.md)均使用原生 `reply`，身份、知识和引用按各实例原有入口提供；两者分别启用 `qqbot_reply_timing`，在发送阶段补齐本账号缺失的 NapCat 连接标识，并让原生后处理首段进入统一计时。只有首条抵扣已耗时，后续分段与研究补充按原速；已有显式路由和接收目标保持。蓝铃两秒连发收集窗口从接收时起算，准备阶段已耗时计入窗口。MaiBot 的新消息打断边界是本轮首条公开消息送达：之前允许重新收集输入，覆盖图片/记忆准备、Planner、原生 Replyer 和首条补等，之后保留本轮后续分段及研究补充，新消息进入下一轮。`planner_interrupt_max_consecutive_count` 仅控制框架原生 Planner；两实例的 [CPA 会话插件](../maibot-lanling/plugins/cpa_session/README.md) 补齐插件模型请求的取消及过期输出拦截，发送等待插件在收到新消息时立即结束旧首条补等，并在提交平台前再次核对源消息。已提交平台且结果未知的发送不能假定已撤回，也不能自动重发。

检查回复速度时，先按同一会话、目标消息和请求对齐接收、排队、模型请求、工具执行与发送时间，同时记录首次有用答复和完整完成时间：

- AstrBot 的 `provider_stats.start_time/end_time` 记录 Agent 运行，不覆盖取得会话锁之前的排队，也不覆盖后续分段发送等待。`QQBotFeatures` 的请求/返回日志起点在其请求 Hook，不能直接当作收到消息到送达的总耗时。
- 云栖先核对旧请求是否占用同会话锁，再核对 `platform_settings.segmented_reply` 的逐段等待，以及 `provider_settings.streaming_response`、`buffer_intermediate_messages` 对公开中间答复的影响。内部推理保持隐藏；正文分段等待与模型继续研究分别计时。
- MaiBot 的 `llm_usage.time_cost` 是模型调用耗时；`planner.finalized.planner.duration_ms`、`final_state.time_records` 是阶段计时，回复工具的 `duration_ms` 还包含回复器与发送流程。用回复工具 `detail.metrics` 分离提示组装、模型生成和工具其余开销，不将回复后的 Planner 收尾算入首次答复延迟。
- 群聊候选、拍一拍静默、实际可见答复及工具失败分开统计，并注明群聊/私聊的样本数。回复旧群消息可能包含模型选择接话的时间间隔，不能把全部间隔归为模型执行。
- 输出余量、图片等待和检索超时是上限。只有实际阶段记录、截断原因或工具返回能证明它们造成了当前等待；配置数值和后台调用次数本身不能代替耗时证据。
- 获准进行隔离模型回放时，保留实际模型参数、上下文及工具调用/结果配对，工具项的 `logical_turn_id` 必须与调用一致；回放输入不合法时先修正输入，不能把失败当作机器人性能结论。
- 新增或调整聊天插件后，除账号 ready 和 OneBot 连接外，还要核对当前进程、当前版本的插件注册完成和启用日志。MaiBot 本地插件必须覆盖 `on_load`、`on_unload` 和 `on_config_update`，初始化中途失败也须能安全卸载；按框架实际 Hook 规格检查模式和错误策略，禁止在不允许 abort 的 Hook 上声明 `ErrorPolicy.ABORT`。SDK 能收集组件、Runner 能加载源码均不代替 Host 注册成功。所需插件完成注册、启用且基础连接恢复只证明启动就绪；回复或发送链变更还须验证原生后处理后的消息命中目标网关、首段及后续段正确送出、明确失败不记成功，不能用启动就绪替代完整发送验证。获准隔离检查时截获网关出口并保留原生发送及路由流程；实际聊天送达须有自然新消息或明确授权的发送证据。

## OpenCode Go

接入 Go 前先核对[官方适用客户端说明](https://opencode.ai/docs/console/go/#where-can-i-use-it)。Go 面向 OpenCode 与类似的编码 Agent；普通 QQ 聊天不属于文档说明的流量类型。补齐 HTTP 头只解决协议要求，不能据此认定普通聊天受支持。客户端使用自身真实的 `User-Agent`，不冒用 OpenCode 或其他编码客户端。

Go 要求每段对话携带稳定的 `x-opencode-session`，直接使用框架已有的真实会话 ID；重试和同一对话的工具续轮复用同一个值。框架内部存在 `session_id` 不等于 HTTP 请求已携带该头；静态 provider headers 也不会自动按对话替换。CPA 应转发客户端已有的会话标识与真实 `User-Agent`，不能给所有对话写死同一个会话值，也不能为每次请求重新生成。

会话透传使用各框架的本地插件：

- AstrBot 使用本地 [CPA 会话透传插件](../astrbot/data/plugins/astrbot_plugin_cpa_session/README.md) 注册的 `cpa_responses` 类型，保留 source ID、模型 ID 与全部生成参数。插件继承原生 Responses 适配器，在 `text_chat`、`text_chat_stream` 接口取得已有 `session_id` 并设置请求级头；中文平台名称按 UTF-8 百分号编码。变更 Provider 类型后完整重启 AstrBot。
- MaiBot 使用各实例的 [CPA 会话透传插件](../maibot-yelin/plugins/cpa_session/README.md)，将指向 CPA 的生成 provider 的 `client_type` 设为 `cpa_responses`。插件通过 Planner、Replyer 的请求 Hook 关联真实会话 ID，增加请求级头后调用原有 `OpenAIResponsesClient.get_response`；保留 provider 名称、模型名和生成参数。没有聊天会话来源的独立辅助调用使用本次逻辑请求 ID。

本项目保留 Go 与 DeepSeek 官网共用 `deepseek-flash` 等模型名称，用于同名模型兜底。渠道优先级、选择与失败回退由 CPA 配置管理；排查时核对实际上游，不因名称相同就判定已选中 Go。Go 的 OpenAI 兼容 Base URL 为 `https://opencode.ai/inference/go/openai/v1`；上游模型 ID 以官网及 CPA 实际配置为准。切换普通生成渠道时，官网联网搜索与嵌入、重排序仍分别遵守本页原有路由约束。

管理页测试缺少会话头时的 400 只证明该测试请求不满足 Go 的要求，不能代替机器人请求链路的判断。接入验收需核对会话头的稳定性、不同对话的隔离、CPA 选中的实际上游，以及工具续轮与读图等直接受影响的行为；调用模型和发送聊天仍遵守项目的测试授权边界。

维护 CPA 请求头时，写入配置后必须核对晚于改动时间的 `config successfully reloaded` 日志或新进程启动记录。没有热加载记录且实际出站仍使用旧请求头时，以现有可执行文件和配置单次重启 CPA，核对新 PID、`8317` 监听和启动日志；保留同名模型兜底与既有凭据。配置生效后，实际模型调用仍按授权边界验收。
