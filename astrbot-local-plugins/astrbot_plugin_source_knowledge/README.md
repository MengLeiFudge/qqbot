# 本地源码知识注入

作者：MengLei

## 插件用途

本插件在 AstrBot 调用 LLM 前，按群号和问题文本检索本机源码树，把少量可信源码片段注入本轮请求。

它用于没有 Embedding 或 AstrBot 原生知识库不可用时的源码知识兜底，尤其是戴森球计划本体、模组、shapez 和 Factorio 模组相关问题。

## 事件监听器

- `inject_source_knowledge`
  - 触发时机：LLM 请求前。
  - 作用：判断当前群和问题是否命中配置的源码领域，检索本机源码并注入少量证据片段。
  - 不发送消息，只影响本轮 LLM 上下文。

## 配置项

- `enabled_groups`
  - 为空时不按群限制。
  - 可填写群号列表限制启用范围。
- `source_roots`
  - 源码根配置。
  - 格式由插件解析为领域名和本机路径。
- `max_results`
  - 最多注入多少个匹配结果。
- `max_chars`
  - 最多注入多少字符。

## 可信依据

- 优先：源码、反编译源码、源码邻近 README、设计文档、配置数据。
- 补充：群聊、群文件、攻略和 release notes 只能作为候选，不作为最终事实。

## 数据与安全边界

- 只读明确配置的源码根。
- 跳过 `.git`、`.codex`、`bin`、`obj`、`.vs`、`.idea`、`packages`、`node_modules`、`logs`、缓存和密钥类文件。
- 不读取私聊、token、QQ 登录态、数据库密钥、运行日志或本仓库运行态 `data`。
