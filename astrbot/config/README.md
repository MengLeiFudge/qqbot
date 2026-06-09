# AstrBot local config templates

本目录只放可提交的本机配置示例，不放真实运行数据。

可用以下命令从当前运行态重新导出示例：

```bash
python3 scripts/export-astrbot-config-examples.py
```

导出内容包括 `cmd_config.example.json`、`personas.example.json` 和 `plugins/*.example.json`。脚本会剔除 LLM provider/model/provider_sources/provider_settings/fallback/image-caption/embedding 路由，并脱敏 key、token、secret、password、cookie、authorization 等字段。

真实 AstrBot 运行数据位于仓库根目录的 `data/astrbot/`，已被根 `.gitignore` 排除。常见敏感项包括：

- Dashboard 密码、JWT secret、TOTP secret。
- Provider API key。
- OneBot / 平台 token。
- HAPI connector access token、Cloudflare Access client secret。
- 插件数据库、长期记忆、会话数据和未脱敏运行态数据。

初始化新机器时，先启动 AstrBot 生成默认配置，再参考本目录的示例补充本机值。

天使/恶魔人格文本只从 AstrBot WebUI 人格配置导出为 `personas.example.json`；本地插件不再内嵌或覆盖固定人设提示词。
