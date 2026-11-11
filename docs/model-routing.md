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
