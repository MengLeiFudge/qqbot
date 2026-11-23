# QQBot 共享 DSP 索引

云栖实例维护一套 DSP 正文、SQLite FTS5 和 FAISS 索引。其他账号使用 `127.0.0.1:8081` 的现有检索接口。服务只监听本机回环。健康和查询路径分别是 `GET /v1/knowledge/dsp/health` 和 `POST /v1/knowledge/dsp/search`。

首次接管时，停止旧写入方后确认快照中的正文、FTS、FAISS 和增量分片清单属于同一版。用 `storage.import_snapshot` 生成 `dsp.sqlite3`，并把分词停用词保存为同目录的 `stopwords.txt`。云栖通过本机 `[index].storage_dir` 使用仓库根的 `data/shared/dsp-index/`。保留原向量维度、嵌入模型和重排序设置。示例配置默认关闭，切换时只启用云栖的实例。

增量同步按照源码分片摘要只嵌入新增或变动的分片，然后在一个事务里提交正文、全文索引、向量和分片记录。旧索引一直保留到事务成功。查询使用稠密和稀疏召回、归一化融合及重排序；相同查询复用成功结果，分片更新后清理缓存。 [脱敏配置示例](config.example.toml)
