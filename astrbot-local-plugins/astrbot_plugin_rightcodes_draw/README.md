# RightCodes 生图兼容壳

作者：MengLei

## 插件用途

本插件只保留旧插件名，避免运行态或测试里仍引用 `astrbot_plugin_rightcodes_draw` 时直接加载失败。

实际 RightCodes 生图命令、积分、模型价格和失败退款逻辑已经迁入 `棉花糖功能合集` 插件。

## 当前状态

- 不注册群聊命令。
- 不监听消息事件。
- 启动时只记录一条迁移提示日志。

## 请使用的新入口

- `棉花糖生图 [模型名] <提示词>`
- `生图模型`
- `生图价格`
- `查看积分`
- `balance`
- `points`

## 数据边界

- 生图积分仍复用 `data\nonebot2\run\ai\draw_points.json`。
- RightCodes API Key 仍从环境变量读取。
- 本兼容壳不再直接读写积分或调用 RightCodes API。
