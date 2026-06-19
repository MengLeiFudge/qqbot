# meme_manager 本地表情包管理器

这是本仓库维护的 AstrBot 本地插件版本，基于上游 `astrbot_plugin_meme_manager` 改造。

## 事实源

- 插件源码：`astrbot-local-plugins/meme_manager/`
- 运行态插件目录：`data/astrbot/data/plugins/meme_manager/`
- 运行态图片目录：`data/astrbot/data/plugin_data/meme_manager/memes/`
- 单图语义索引：`data/astrbot/data/plugin_data/meme_manager/meme_index.json`
- 类别描述兼容文件：`data/astrbot/data/plugin_data/meme_manager/memes_data.json`

`data/memes/mlj_pack/` 只作为历史整理结果和迁移来源保留，不再作为日常运行事实源。

## 使用方式

私聊机器人发送：

```text
表情管理 开启管理后台
```

管理后台支持：

- 本地图片预览
- 搜索类别、文件名、标题、说明、关键词和场景
- 新建、重命名、删除和清空类别
- 单图编辑显示标题、画面说明、关键词、适用场景、禁用场景、强度、权重和自动发送开关
- 拖拽移动、批量移动、批量删除、批量复制
- 从旧 `mlj_pack` 复制/合并迁移图片和元数据

## 发送逻辑

LLM 仍只负责决定是否使用表情和粗类别标签。

插件本地 selector 不额外调用 LLM，会按下面信息选择具体图片：

- 类别
- 单图关键词
- 适用场景
- 禁用场景
- 权重
- 强度
- 近期去重

`auto_send_enabled=false` 的图片不会被自动发送。

## 迁移命令

从旧 `data/memes/mlj_pack/index.json` 迁移：

```bash
python3 tools/maintenance-scripts/migrate-meme-pack-to-manager.py
```

兼容旧命令名：

```bash
python3 tools/maintenance-scripts/sync-meme-pack.py
```

这两个命令只复制/合并到 `meme_manager` 运行态，不删除旧目录。

## 图床边界

上游图床同步代码保留为兼容能力，但本仓库当前表情包设计限定为本地图库优先。日常管理和自动发送以本地 `meme_index.json` 与 `memes/` 为准。
