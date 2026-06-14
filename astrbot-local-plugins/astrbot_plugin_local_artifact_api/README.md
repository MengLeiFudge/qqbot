# 本地产物发布接口

作者：MengLei

## 插件用途

本插件为 AstrBot `full` 模式提供本机兼容 API，让本地构建流程继续通过 QQ 群文件发布 zip、dll 等构建产物。

它主要服务 `AfterBuildEvent.exe 1` 这类本机白名单构建流程，不是群聊指令插件，也不会响应普通聊天。

## 接口

- `POST /admin/api/artifacts/publish-local`
  - 只监听 `127.0.0.1` / `::1` / `localhost`。
  - 校验请求时间、Git 上下文、文件路径和发布元数据。
  - `sha256` 校验 zip 文件本身，`content_sha256` 判断 zip 内部内容是否变化。
  - 通过当前 AstrBot `aiocqhttp` OneBot 连接上传群文件。
  - 同一次请求向同一群上传多个变化文件时，先上传所有文件，最后只引用最后一个文件消息并发送一次发布说明。

## 配置项

- `host`
  - 默认 `127.0.0.1`。
  - 建议保持本机监听，不对局域网或公网开放。
- `port`
  - 默认 `8080`。
  - 也可通过环境变量 `QQBOT_ASTRBOT_ARTIFACT_API_PORT` 覆盖。

## 运行边界

- 只有 `QQBOT_ASTRBOT_FEATURE_MODE=full` 时才启动接口监听。
- `dual` 模式下不抢占 NoneBot2 管理端的 `8080`。
- 不读取 QQ 登录态、token、私聊记录或 AstrBot 运行日志。
- 发布状态和复用服务来自 `data\nonebot2\run`，用于保持 bot1 到 bot2 迁移期间的兼容性。

## 验证重点

- AstrBot full 模式启动日志应出现本插件监听地址。
- 非 localhost 请求应返回 `403`。
- 构建产物发布失败时应返回明确 JSON 错误，不在群聊里泄露本机敏感路径以外的信息。
