# CPA 会话透传

本地 Provider 插件通过 Planner、Replyer 的公开 Hook 取得真实会话 ID，并将其写入请求级 `x-opencode-session`，由 CPA 透传给 OpenCode Go。请求使用自身 UA，版本与插件发布版本一致。

启用 `config.toml` 的 `plugin.enabled`，把 `config/model_config.toml` 中指向 CPA 的生成 provider 的 `client_type` 改成 `cpa_responses`，然后重启 MaiBot。保留 provider 名称、地址、密钥及生成参数。发给 CPA 的模型标识使用 `qqbot-deepseek-flash`。夜凛启动允许表已包含本传输插件。

插件直接调用框架现有的 `OpenAIResponsesClient.get_response`，使用原生请求类型和序列化函数；工具、图像、推理、HTTP 重试与流式读取沿用该客户端。会话关联与原生回放项仅缓存在内存，卸载清空。没有聊天会话来源的独立辅助调用使用本次逻辑请求 ID。

本轮首条公开回复送达前，新消息可以取代旧输入：图片或记忆准备期间收到补充，若 Planner 快照尚未包含补充，就跳过旧模型调用；Planner、Replyer 请求中收到新消息时取消本插件的对应请求。每个新的主动任务以框架分配的 Context Item ID 建立独立轮次，即使沿用相同用户消息，也重新等待自己的首条回执；同一任务的工具续轮保留发送状态。模型刚返回时再次核对，旧规划不执行工具、旧正文不进入发送；原生循环重新收集消息，保留图片、补充文字、人设及完整回复器。首条补等期间由 [qqbot_reply_timing](../qqbot_reply_timing/README.md) 再次核对源消息。

带消息锚点的原生聊天答复在发送前再次检查是否过期。签到等插件指令答复走独立发送流程，也不计入普通聊天的首条送达。首条明确发送成功后，本轮后续分段和研究补充继续完成，新消息由下一轮处理。发送失败不关闭取消资格。已经提交到平台、结果未知的发送需要保留原状态。取消的模型请求返回 `cancelled`、空输出和未知用量。

RPC 和框架源码均无需修改。模型路由与 CPA 同名渠道兜底见根工作区 [模型 API 路由](../../../docs/model-routing.md#opencode-go)。
