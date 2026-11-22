# 框架与插件部署

QQBot 在一个 Git 仓库内维护自研插件、账号编排和部署脚本。当前账号使用官方 MaiBot 发布包。版本和插件分发范围见 [部署清单](../deployment/frameworks.json)，账号和启动选择见 [账号清单](../napcat/accounts.json)。

## 安装和更新

Windows 使用 Python 3.11 或更新版本的 `py` 启动器、PowerShell 5.1 和 `uv`。先克隆 `qqbot`，再安装所需框架：

```powershell
.\scripts\update-all.bat maibot
```

更新时在清单中填写官方稳定 Release 的 tag 和对应提交，再运行同一命令。安装器先准备官方提交的源码归档，再停对应框架进程并替换框架文件。各账号的配置、数据、插件配置和市场插件保留在原运行目录。旧框架文件归档到 `.codex/trash/framework-<Target>-*/previous/`。

已装版本与清单一致时，安装器只同步自研插件。切换版本后按原账号 Target 启动；首次启动或依赖环境需重建时省略 `-SkipInstall`。首次部署需要按示例填写实际配置，并通过框架原生流程确认条款。[MaiBot 示例](../deployment/maibot/config-examples/README.md)

MaiBot 内置插件管理使用其原生 `config.toml`，首次安装写入 `plugin.enabled = false`。准备配置时，已启用插件及内置管理配置须填写对应插件声明的 `plugin.config_version`，例如内置管理的 `1.2.0`。夜凛设为 `autoStart=false`，安装流程只准备其文件。[MaiBot 聊天实例](chat-instances.md)

## 修改和同步自研插件

1. 修改 `plugins/astrbot/` 或 `plugins/maibot/` 中的源码。风铃和夜凛共同覆盖的文件在 `plugins/overrides/chat-only/`，夜凛专用覆盖在 `plugins/overrides/yelin/`。修改有覆盖的文件时同时检查相应实例。
2. 编译检查后执行 `.\scripts\deploy-plugins.ps1 <Target>`。同步只写清单里的自研插件源码和资源，保留 `config.toml`、已有图床配置、市场插件和运行数据。删除或改名时要显式归档运行目录中的旧文件。
3. 按框架的重载方式生效，再查看插件加载日志。[插件热重载](chat-instances.md#插件改动与热重载)

Windows 实例的生图、群文件发布、养鲲和落樱之都使用公共插件提供的文件锁。部署这些插件时一并同步 `qqbot_common`。迁移含共享检索的实例时，正文与索引须作为同一份快照接续。[DSP 索引部署](../plugins/maibot/qqbot_dsp_index/README.md)

## 恢复

启动失败时保留启动日志。要回到归档版本，先停对应框架进程，将当前框架文件移入新归档，再把 `previous/` 中的旧文件放回原路径。每个实例原位保留的数据目录不参与替换；MaiBot 的 `/pm` 配置随 `src/` 保存在框架归档内。框架升级前另做实例配置和数据库备份，避免框架自身数据迁移影响回退。安装出错时会撤回框架文件的移动。若插件同步报错，按日志修复后重新部署。
