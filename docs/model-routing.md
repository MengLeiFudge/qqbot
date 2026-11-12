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

## OpenCode Go

接入 Go 前先核对[官方适用客户端说明](https://opencode.ai/docs/console/go/#where-can-i-use-it)。Go 面向 OpenCode 与类似的编码 Agent；普通 QQ 聊天不属于文档说明的流量类型。补齐 HTTP 头只解决协议要求，不能据此认定普通聊天受支持。客户端使用自身真实的 `User-Agent`，不冒用 OpenCode 或其他编码客户端。

Go 要求每段对话携带稳定的 `x-opencode-session`，直接使用框架已有的真实会话 ID；重试和同一对话的工具续轮复用同一个值。框架内部存在 `session_id` 不等于 HTTP 请求已携带该头；静态 provider headers 也不会自动按对话替换。CPA 应转发客户端已有的会话标识与真实 `User-Agent`，不能给所有对话写死同一个会话值，也不能为每次请求重新生成。

会话透传使用各框架的本地插件：

- AstrBot 使用本地 [CPA 会话透传插件](../astrbot/data/plugins/astrbot_plugin_cpa_session/README.md) 注册的 `cpa_responses` 类型，保留 source ID、模型 ID 与全部生成参数。插件继承原生 Responses 适配器，在 `text_chat`、`text_chat_stream` 接口取得已有 `session_id` 并设置请求级头；中文平台名称按 UTF-8 百分号编码。变更 Provider 类型后完整重启 AstrBot。
- MaiBot 使用各实例的 [CPA 会话透传插件](../maibot-yelin/plugins/cpa_session/README.md)，将指向 CPA 的生成 provider 的 `client_type` 设为 `cpa_responses`。插件通过 Planner、Replyer 的请求 Hook 关联真实会话 ID，增加请求级头后调用原有 `OpenAIResponsesClient.get_response`；保留 provider 名称、模型名和生成参数。没有聊天会话来源的独立辅助调用使用本次逻辑请求 ID。

本项目保留 Go 与 DeepSeek 官网共用 `deepseek-flash` 等模型名称，用于同名模型兜底。渠道优先级、选择与失败回退由 CPA 配置管理；排查时核对实际上游，不因名称相同就判定已选中 Go。Go 的 OpenAI 兼容 Base URL 为 `https://opencode.ai/inference/go/openai/v1`；上游模型 ID 以官网及 CPA 实际配置为准。切换普通生成渠道时，官网联网搜索与嵌入、重排序仍分别遵守本页原有路由约束。

管理页测试缺少会话头时的 400 只证明该测试请求不满足 Go 的要求，不能代替机器人请求链路的判断。接入验收需核对会话头的稳定性、不同对话的隔离、CPA 选中的实际上游，以及工具续轮与读图等直接受影响的行为；调用模型和发送聊天仍遵守项目的测试授权边界。

维护 CPA 请求头时，写入配置后必须核对晚于改动时间的 `config successfully reloaded` 日志或新进程启动记录。没有热加载记录且实际出站仍使用旧请求头时，以现有可执行文件和配置单次重启 CPA，核对新 PID、`8317` 监听和启动日志；保留同名模型兜底与既有凭据。配置生效后，实际模型调用仍按授权边界验收。
