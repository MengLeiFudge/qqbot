from __future__ import annotations

from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from threading import Lock
from uuid import uuid4
import json
import re
import sqlite3

import faiss
import jieba
import numpy as np

from .catalog import SourceShard


DIMENSION = 1024
_RECALL_LIMIT = 24
_TERM = re.compile(r"\w")


def _read_only(path: Path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _validate_seed(db: sqlite3.Connection, index, manifest: dict) -> None:
    if manifest["kb_name"] != "dsp-major-mods" or index.d != DIMENSION or index.metric_type != faiss.METRIC_L2:
        raise ValueError("DSP 快照的知识库、维度或距离算法不兼容")
    sources = {row["doc_id"]: row["chunk_count"] for row in manifest["shards"].values()}
    chunks = dict(db.execute("SELECT kb_doc_id, count(*) FROM documents GROUP BY kb_doc_id"))
    if not sources or chunks != sources:
        raise ValueError("DSP 分片清单和正文库不一致")
    rows = {row[0] for row in db.execute("SELECT id FROM documents")}
    fts = {row[0] for row in db.execute("SELECT id FROM documents_fts_docsize")}
    if rows != fts or rows != set(faiss.vector_to_array(index.id_map)) or len(rows) != index.ntotal:
        raise ValueError("DSP 正文、全文索引和向量 ID 不一致")


def import_snapshot(seed: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError("DSP 目标库已存在，保留现有数据")
    manifest = json.loads((seed / "index_manifest.json").read_text(encoding="utf-8"))
    index = faiss.read_index(str(seed / "index.faiss"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        with closing(_read_only(seed / "doc.db")) as source, closing(sqlite3.connect(pending)) as db:
            _validate_seed(source, index, manifest)
            source.backup(db)
            with db:
                db.execute("CREATE TABLE dsp_state (id INTEGER PRIMARY KEY CHECK (id=1), manifest TEXT NOT NULL, vectors BLOB NOT NULL)")
                db.execute("INSERT INTO dsp_state VALUES (1, ?, ?)", (json.dumps(manifest), faiss.serialize_index(index).tobytes()))
        pending.rename(destination)
    finally:
        pending.unlink(missing_ok=True)


class DspIndex:
    def __init__(self, path: Path, stopwords: Path) -> None:
        self._path = path
        words = stopwords.read_text(encoding="utf-8").splitlines()
        self._stopwords = frozenset(word.strip() for word in words if word.strip())
        self._lock = Lock()
        with closing(_read_only(path)) as db:
            manifest, data = db.execute("SELECT manifest, vectors FROM dsp_state WHERE id=1").fetchone()
        self._manifest = json.loads(manifest)
        self._index = faiss.deserialize_index(np.frombuffer(data, dtype=np.uint8))

    def status(self) -> dict:
        manifest = self._manifest
        return {
            "knowledge_base": manifest["kb_name"],
            "shard_count": len(manifest["shards"]),
            "file_count": sum(shard["file_count"] for shard in manifest["shards"].values()),
            "chunk_count": sum(shard["chunk_count"] for shard in manifest["shards"].values()),
            "last_completed_at": manifest.get("last_completed_at", ""),
        }

    def source_digests(self) -> dict[str, str]:
        return {key: row["digest"] for key, row in self._manifest["shards"].items()}

    def candidates(self, query: str, vector: np.ndarray | None, limit: int) -> list[str]:
        expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in self._tokens(query))
        with self._lock, closing(_read_only(self._path)) as db:
            dense = self._dense(db, vector) if vector is not None else []
            sparse = db.execute(
                "SELECT d.doc_id, d.text, -bm25(documents_fts) AS score "
                "FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid "
                "WHERE documents_fts MATCH ? ORDER BY score DESC, d.id ASC LIMIT ?",
                (expression, _RECALL_LIMIT),
            ).fetchall() if expression else []
        return _fuse(dense, sparse, limit)

    def _dense(self, db: sqlite3.Connection, vector: np.ndarray) -> list[tuple[str, str, float]]:
        distances, indices = self._index.search(vector.reshape(1, -1), _RECALL_LIMIT)
        identifiers = list(map(int, indices[0]))
        parameters = ",".join("?" for _ in identifiers)
        docs = {row[0]: row[1:] for row in db.execute(f"SELECT id, doc_id, text FROM documents WHERE id IN ({parameters})", identifiers)}
        return [(*docs[identifier], 1.0 - float(distance) / 2.0)
                for identifier, distance in zip(identifiers, distances[0]) if identifier in docs]

    def replace_shards(self, replacements: Sequence[tuple[SourceShard, np.ndarray]], removed: set[str], completed_at: str) -> None:
        if not replacements and not removed:
            return
        with self._lock, closing(sqlite3.connect(self._path.resolve().as_uri() + "?mode=rw", uri=True)) as db:
            index = faiss.clone_index(self._index)
            shards = dict(self._manifest["shards"])
            manifest = {**self._manifest, "shards": shards, "last_completed_at": completed_at}
            with db:
                for key in removed | {shard.key for shard, _ in replacements}:
                    if old := shards.pop(key, None):
                        rows = [row[0] for row in db.execute("SELECT id FROM documents WHERE kb_doc_id = ?", (old["doc_id"],))]
                        index.remove_ids(np.asarray(rows, dtype=np.int64))
                        db.executemany("DELETE FROM documents_fts WHERE rowid = ?", ((row,) for row in rows))
                        db.execute("DELETE FROM documents WHERE kb_doc_id = ?", (old["doc_id"],))
                for shard, vectors in replacements:
                    doc_id = uuid4().hex
                    row_ids: list[int] = []
                    for i, chunk in enumerate(shard.chunks):
                        metadata = json.dumps({"kb_id": manifest["kb_id"], "kb_doc_id": doc_id, "chunk_index": i})
                        row = db.execute(
                            "INSERT INTO documents (doc_id, text, metadata) VALUES (?, ?, ?)", (uuid4().hex, chunk, metadata),
                        ).lastrowid
                        db.execute("INSERT INTO documents_fts (rowid, search_text) VALUES (?, ?)", (row, " ".join(self._tokens(chunk))))
                        row_ids.append(row)
                    index.add_with_ids(vectors, np.asarray(row_ids, dtype=np.int64))
                    shards[shard.key] = {"digest": shard.digest, "doc_id": doc_id, "chunk_count": len(row_ids), "file_count": shard.file_count}
                db.execute("UPDATE dsp_state SET manifest = ?, vectors = ? WHERE id = 1", (json.dumps(manifest), faiss.serialize_index(index).tobytes()))
            self._index = index
            self._manifest = manifest

    def _tokens(self, text: str):
        for token in jieba.cut(text):
            token = token.strip()
            if token and token not in self._stopwords and _TERM.search(token):
                yield token


def _rank(rows: list[tuple[str, str, float]]) -> dict[str, tuple[float, int]]:
    if not rows:
        return {}
    low = min(row[2] for row in rows)
    width = max(row[2] for row in rows) - low
    return {key: ((score - low) / width if width else 1.0, rank)
            for rank, (key, _, score) in enumerate(rows, 1)}


def _fuse(dense: list[tuple[str, str, float]], sparse: list[tuple[str, str, float]], limit: int) -> list[str]:
    dense_rank = _rank(dense)
    sparse_rank = _rank(sparse)
    texts = {key: text for key, text, _ in dense + sparse}

    def sort_key(key: str):
        d_score, d_rank = dense_rank.get(key, (0.0, float("inf")))
        s_score, s_rank = sparse_rank.get(key, (0.0, float("inf")))
        return (-0.9 * d_score - 0.1 * s_score, -1 / (60 + d_rank) - 1 / (60 + s_rank), d_rank, s_rank, key)

    distinct = dict.fromkeys(texts[key] for key in sorted(texts, key=sort_key))
    return list(distinct)[:limit]
