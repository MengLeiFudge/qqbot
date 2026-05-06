from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from qqbot.services.ai_gateway import is_safety_rejection_text


VALID_DIRECTIONS = {"incoming", "bot"}


@dataclass(frozen=True, slots=True)
class ChatMemoryRecord:
    id: int
    group_id: str
    message_id: str
    direction: str
    user_id: str
    sender_name: str
    text: str
    summary: str
    tags: tuple[str, ...]
    timestamp: int
    has_image: bool = False
    has_at: bool = False
    reply_message_id: str = ""
    reply_user_id: str = ""
    reply_outline: str = ""


class ChatMemoryStore:
    def __init__(self, data_root: Path, db_path: Path | None = None) -> None:
        self.data_root = Path(data_root)
        self.db_path = db_path or self.data_root / "ai" / "chat_memory.sqlite3"

    def append_message(
        self,
        *,
        group_id: int | str,
        message_id: int | str | None,
        direction: str,
        user_id: int | str,
        sender_name: str,
        text: str,
        timestamp: int | float,
        summary: str = "",
        tags: tuple[str, ...] | list[str] | None = None,
        has_image: bool = False,
        has_at: bool = False,
        reply_message_id: int | str | None = None,
        reply_user_id: int | str | None = None,
        reply_outline: str = "",
    ) -> bool:
        normalized_text = text.strip()
        if not normalized_text or is_safety_rejection_text(normalized_text):
            return False
        if direction not in VALID_DIRECTIONS:
            raise ValueError(f"Unsupported chat memory direction: {direction}")

        normalized_tags = tuple(dict.fromkeys([*(tags or ()), *infer_rule_tags(normalized_text)]))
        payload = {
            "group_id": str(group_id),
            "message_id": str(message_id or ""),
            "direction": direction,
            "user_id": str(user_id),
            "sender_name": sender_name.strip() or str(user_id),
            "text": normalized_text,
            "summary": summary.strip(),
            "tags": json.dumps(normalized_tags, ensure_ascii=False),
            "timestamp": int(timestamp),
            "has_image": 1 if has_image else 0,
            "has_at": 1 if has_at else 0,
            "reply_message_id": str(reply_message_id or ""),
            "reply_user_id": str(reply_user_id or ""),
            "reply_outline": reply_outline.strip(),
        }
        with self._connect() as conn:
            self._ensure_schema(conn)
            existing_id = self._find_existing_id(
                conn,
                payload["group_id"],
                payload["message_id"],
                direction,
            )
            if existing_id is not None:
                return False
            cursor = conn.execute(
                """
                INSERT INTO messages (
                    group_id, message_id, direction, user_id, sender_name,
                    text, summary, tags, timestamp, has_image, has_at,
                    reply_message_id, reply_user_id, reply_outline
                )
                VALUES (
                    :group_id, :message_id, :direction, :user_id, :sender_name,
                    :text, :summary, :tags, :timestamp, :has_image, :has_at,
                    :reply_message_id, :reply_user_id, :reply_outline
                )
                """,
                payload,
            )
            row_id = int(cursor.lastrowid)
            if self._fts_available(conn):
                self._index_fts(conn, row_id, payload)
            return True

    def search_messages(
        self,
        group_id: int | str,
        query: str,
        *,
        limit: int = 6,
    ) -> tuple[ChatMemoryRecord, ...]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0 or not self.db_path.exists():
            return ()

        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = self._search_with_fts(conn, str(group_id), normalized_query, limit)
            if len(rows) < limit:
                seen_ids = {int(row["id"]) for row in rows}
                rows.extend(
                    row
                    for row in self._search_with_like(conn, str(group_id), normalized_query, limit)
                    if int(row["id"]) not in seen_ids
                )
        records = tuple(self._record_from_row(row) for row in rows[:limit])
        return records

    def remove_group(self, group_id: int | str) -> bool:
        if not self.db_path.exists():
            return False
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT id FROM messages WHERE group_id = ?",
                (str(group_id),),
            ).fetchall()
            if not rows:
                return False
            ids = [int(row["id"]) for row in rows]
            if self._fts_available(conn):
                conn.executemany(
                    "DELETE FROM messages_fts WHERE message_rowid = ?",
                    [(row_id,) for row_id in ids],
                )
            conn.execute("DELETE FROM messages WHERE group_id = ?", (str(group_id),))
        return True

    def backfill_from_group_logs(self) -> int:
        root = self.data_root / "admin" / "group_messages"
        if not root.exists():
            return 0

        imported = 0
        for path in sorted(root.glob("*.json")):
            if not path.stem.isdigit():
                continue
            raw_records = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw_records, list):
                continue
            for raw in raw_records:
                if not isinstance(raw, dict):
                    continue
                direction = str(raw.get("direction", "")).strip()
                text = str(raw.get("text", "")).strip()
                if direction not in VALID_DIRECTIONS or not text:
                    continue
                if self.append_message(
                    group_id=path.stem,
                    message_id=raw.get("message_id", ""),
                    direction=direction,
                    user_id=raw.get("user_id", ""),
                    sender_name=str(raw.get("sender_name", "")).strip(),
                    text=text,
                    timestamp=int(raw.get("timestamp", 0)),
                ):
                    imported += 1
        return imported

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                message_id TEXT NOT NULL DEFAULT '',
                direction TEXT NOT NULL,
                user_id TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                text TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                timestamp INTEGER NOT NULL,
                has_image INTEGER NOT NULL DEFAULT 0,
                has_at INTEGER NOT NULL DEFAULT 0,
                reply_message_id TEXT NOT NULL DEFAULT '',
                reply_user_id TEXT NOT NULL DEFAULT '',
                reply_outline TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_unique_message
            ON messages(group_id, direction, message_id)
            WHERE message_id != ''
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_group_time ON messages(group_id, timestamp DESC)"
        )
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    message_rowid UNINDEXED,
                    text,
                    summary,
                    tags,
                    sender_name,
                    reply_outline
                )
                """
            )
        except sqlite3.OperationalError:
            pass

    def _fts_available(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'messages_fts'"
        ).fetchone()
        return row is not None

    def _index_fts(self, conn: sqlite3.Connection, row_id: int, payload: dict[str, object]) -> None:
        conn.execute("DELETE FROM messages_fts WHERE message_rowid = ?", (row_id,))
        conn.execute(
            """
            INSERT INTO messages_fts(message_rowid, text, summary, tags, sender_name, reply_outline)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                payload["text"],
                payload["summary"],
                payload["tags"],
                payload["sender_name"],
                payload["reply_outline"],
            ),
        )

    def _search_with_fts(
        self,
        conn: sqlite3.Connection,
        group_id: str,
        query: str,
        limit: int,
    ) -> list[sqlite3.Row]:
        if not self._fts_available(conn):
            return []
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
        try:
            return list(
                conn.execute(
                    """
                    SELECT messages.*
                    FROM messages_fts
                    JOIN messages ON messages.id = messages_fts.message_rowid
                    WHERE messages.group_id = ?
                      AND messages_fts MATCH ?
                    ORDER BY bm25(messages_fts), messages.timestamp DESC, messages.id DESC
                    LIMIT ?
                    """,
                    (group_id, fts_query, limit),
                ).fetchall()
            )
        except sqlite3.OperationalError:
            return []

    def _search_with_like(
        self,
        conn: sqlite3.Connection,
        group_id: str,
        query: str,
        limit: int,
    ) -> list[sqlite3.Row]:
        terms = build_like_terms(query)
        if not terms:
            return []

        clauses: list[str] = []
        params: list[object] = [group_id]
        for term in terms:
            like = f"%{term}%"
            clauses.append(
                "(text LIKE ? OR summary LIKE ? OR tags LIKE ? OR sender_name LIKE ? OR reply_outline LIKE ?)"
            )
            params.extend([like, like, like, like, like])
        params.append(limit)
        return list(
            conn.execute(
                f"""
                SELECT *
                FROM messages
                WHERE group_id = ?
                  AND ({' OR '.join(clauses)})
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        )

    def _find_existing_id(
        self,
        conn: sqlite3.Connection,
        group_id: str,
        message_id: str,
        direction: str,
    ) -> int | None:
        if not message_id:
            return None
        row = conn.execute(
            """
            SELECT id FROM messages
            WHERE group_id = ? AND message_id = ? AND direction = ?
            """,
            (group_id, message_id, direction),
        ).fetchone()
        return None if row is None else int(row["id"])

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> ChatMemoryRecord:
        return ChatMemoryRecord(
            id=int(row["id"]),
            group_id=str(row["group_id"]),
            message_id=str(row["message_id"] or ""),
            direction=str(row["direction"]),
            user_id=str(row["user_id"]),
            sender_name=str(row["sender_name"]),
            text=str(row["text"]),
            summary=str(row["summary"] or ""),
            tags=tuple(json.loads(str(row["tags"] or "[]"))),
            timestamp=int(row["timestamp"]),
            has_image=bool(row["has_image"]),
            has_at=bool(row["has_at"]),
            reply_message_id=str(row["reply_message_id"] or ""),
            reply_user_id=str(row["reply_user_id"] or ""),
            reply_outline=str(row["reply_outline"] or ""),
        )


def infer_rule_tags(text: str) -> tuple[str, ...]:
    normalized = text.lower()
    tags: list[str] = []
    if any(keyword in normalized for keyword in ("知识库", "聊天记录", "历史聊天", "数据库", "标签", "分门别类")):
        tags.append("知识库")
    if any(keyword in normalized for keyword in ("ai", "模型", "prompt", "提示词")):
        tags.append("AI")
    if any(keyword in normalized for keyword in ("codex", "代码", "项目", "提交")):
        tags.append("Codex")
    if any(keyword in normalized for keyword in ("群管", "禁言", "复读", "管理")):
        tags.append("群管")
    return tuple(dict.fromkeys(tags))


def build_fts_query(query: str) -> str:
    return " OR ".join(f'"{term}"' for term in build_like_terms(query))


def build_like_terms(query: str) -> list[str]:
    terms = [term.strip() for term in query.replace("，", " ").replace(",", " ").split()]
    return [term for term in dict.fromkeys(terms) if term]
