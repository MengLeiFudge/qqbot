# AstrBot 运行时泄漏守卫

作者：MengLei

## 插件用途

本插件用于本地 AstrBot 部署的兜底防护：当 AstrBot 内部 Agent 或 LLM 请求异常被拼成普通消息准备发给 QQ 时，拦截这类内部错误文本，避免用户在群聊或私聊里看到原始异常。

它不处理普通聊天，不参与命令匹配，也不修改模型选择。

## 拦截规则

- 当前拦截前缀：
  - `Error occurred while processing agent request:`
- 命中后：
  - 不向 QQ 发送该消息。
  - 在 AstrBot 日志中记录被拦截的 session、是否群聊和原始错误文本。

## 事件入口

本插件通过启动时 patch `AiocqhttpMessageEvent.send_message` 接入消息发送边界，因此管理端不会显示普通群聊指令。

## 安全边界

- 只拦截已准备发送的 Plain 文本链。
- 不读取私聊历史、QQ 登录态、token 或数据库密钥。
- 不吞掉普通业务异常日志，只阻止内部错误原文发到 QQ。
- 不修改 AstrBot Core 源码；守卫只在插件加载后对运行时类方法做本地 patch。

## 验证重点

- 启动日志应显示本插件 by MengLei 和 `aiocqhttp internal error guard installed`。
- 触发内部 Agent 错误时，QQ 侧不应收到原始 `Error occurred while processing agent request:` 文本。
