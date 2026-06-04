# AstrBot local config templates

本目录只放可提交的本机配置示例，不放真实运行数据。

真实 AstrBot 运行数据位于仓库根目录的 `data/astrbot/`，已被根 `.gitignore` 排除。常见敏感项包括：

- Dashboard 密码、JWT secret、TOTP secret。
- Provider API key。
- OneBot / 平台 token。
- HAPI connector access token、Cloudflare Access client secret。
- 插件数据库、长期记忆、人格数据和会话数据。

初始化新机器时，先启动 AstrBot 生成默认配置，再参考本目录的示例补充本机值。
