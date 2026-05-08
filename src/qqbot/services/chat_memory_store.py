from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
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
    topics: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    importance: float = 0.5
    confidence: float = 0.6


@dataclass(frozen=True, slots=True)
class ChatMemoryFact:
    id: int
    group_id: str
    subject: str
    predicate: str
    object: str
    confidence: float
    source_message_ids: tuple[str, ...]
    topics: tuple[str, ...]
    entities: tuple[str, ...]
    updated_at: int


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
        topics: tuple[str, ...] | list[str] | None = None,
        entities: tuple[str, ...] | list[str] | None = None,
        importance: float | None = None,
        confidence: float | None = None,
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
        normalized_topics = tuple(
            dict.fromkeys([*(topics or ()), *infer_rule_topics(normalized_text)])
        )
        normalized_entities = tuple(
            dict.fromkeys(
                [
                    sender_name.strip() or str(user_id),
                    str(user_id),
                    *(entities or ()),
                    *extract_rule_entities(normalized_text),
                ]
            )
        )
        payload = {
            "group_id": str(group_id),
            "message_id": str(message_id or ""),
            "direction": direction,
            "user_id": str(user_id),
            "sender_name": sender_name.strip() or str(user_id),
            "text": normalized_text,
            "summary": summary.strip(),
            "tags": json.dumps(normalized_tags, ensure_ascii=False),
            "topics": json.dumps(normalized_topics, ensure_ascii=False),
            "entities": json.dumps(normalized_entities, ensure_ascii=False),
            "importance": float(importance if importance is not None else infer_importance(normalized_text)),
            "confidence": float(confidence if confidence is not None else 0.6),
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
                    text, summary, tags, topics, entities, importance, confidence,
                    timestamp, has_image, has_at,
                    reply_message_id, reply_user_id, reply_outline
                )
                VALUES (
                    :group_id, :message_id, :direction, :user_id, :sender_name,
                    :text, :summary, :tags, :topics, :entities, :importance, :confidence,
                    :timestamp, :has_image, :has_at,
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
            search_limit = max(limit * 4, limit)
            rows = self._search_with_fts(conn, str(group_id), normalized_query, search_limit)
            if len(rows) < limit:
                seen_ids = {int(row["id"]) for row in rows}
                rows.extend(
                    row
                    for row in self._search_with_like(
                        conn,
                        str(group_id),
                        normalized_query,
                        search_limit,
                    )
                    if int(row["id"]) not in seen_ids
                )
        records = tuple(
            record
            for _, record in sorted(
                (
                    (
                        score_message_record(self._record_from_row(row), normalized_query),
                        self._record_from_row(row),
                    )
                    for row in rows
                ),
                key=lambda item: (-item[0], -item[1].timestamp, -item[1].id),
            )[:limit]
        )
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
                conn.execute("DELETE FROM facts_fts WHERE group_id = ?", (str(group_id),))
            conn.execute("DELETE FROM messages WHERE group_id = ?", (str(group_id),))
            conn.execute("DELETE FROM facts WHERE group_id = ?", (str(group_id),))
        return True

    def extract_facts_from_recent_messages(
        self,
        group_id: int | str,
        *,
        limit: int = 100,
    ) -> int:
        if limit <= 0:
            return 0
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE group_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (str(group_id), limit),
            ).fetchall()
            inserted = 0
            for row in reversed(rows):
                record = self._record_from_row(row)
                for fact in extract_rule_facts(record):
                    if self._upsert_fact(conn, fact):
                        inserted += 1
            return inserted

    def search_facts(
        self,
        group_id: int | str,
        query: str,
        *,
        limit: int = 6,
    ) -> tuple[ChatMemoryFact, ...]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0 or not self.db_path.exists():
            return ()
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = self._search_facts_with_fts(conn, str(group_id), normalized_query, limit * 4)
            if len(rows) < limit:
                seen_ids = {int(row["id"]) for row in rows}
                rows.extend(
                    row
                    for row in self._search_facts_with_like(
                        conn,
                        str(group_id),
                        normalized_query,
                        limit * 4,
                    )
                    if int(row["id"]) not in seen_ids
                )
        facts = tuple(
            fact
            for _, fact in sorted(
                (
                    (score_fact(self._fact_from_row(row), normalized_query), self._fact_from_row(row))
                    for row in rows
                ),
                key=lambda item: (-item[0], -item[1].updated_at, -item[1].id),
            )[:limit]
        )
        return facts

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

    def list_group_ids(self) -> tuple[int, ...]:
        if not self.db_path.exists():
            return ()
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT DISTINCT group_id FROM messages ORDER BY group_id"
            ).fetchall()
        return tuple(int(row["group_id"]) for row in rows if str(row["group_id"]).isdigit())

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
                topics TEXT NOT NULL DEFAULT '[]',
                entities TEXT NOT NULL DEFAULT '[]',
                importance REAL NOT NULL DEFAULT 0.5,
                confidence REAL NOT NULL DEFAULT 0.6,
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
        self._ensure_column(conn, "messages", "topics", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column(conn, "messages", "entities", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column(conn, "messages", "importance", "REAL NOT NULL DEFAULT 0.5")
        self._ensure_column(conn, "messages", "confidence", "REAL NOT NULL DEFAULT 0.6")
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    message_rowid UNINDEXED,
                    text,
                    summary,
                    tags,
                    topics,
                    entities,
                    sender_name,
                    reply_outline
                )
                """
            )
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.7,
                source_message_ids TEXT NOT NULL DEFAULT '[]',
                topics TEXT NOT NULL DEFAULT '[]',
                entities TEXT NOT NULL DEFAULT '[]',
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_unique
            ON facts(group_id, subject, predicate, object)
            """
        )
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                    fact_rowid UNINDEXED,
                    group_id UNINDEXED,
                    subject,
                    predicate,
                    object,
                    topics,
                    entities
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

    def _facts_fts_available(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'facts_fts'"
        ).fetchone()
        return row is not None

    def _index_fts(self, conn: sqlite3.Connection, row_id: int, payload: dict[str, object]) -> None:
        conn.execute("DELETE FROM messages_fts WHERE message_rowid = ?", (row_id,))
        conn.execute(
            """
            INSERT INTO messages_fts(
                message_rowid, text, summary, tags, topics, entities, sender_name, reply_outline
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                payload["text"],
                payload["summary"],
                payload["tags"],
                payload["topics"],
                payload["entities"],
                payload["sender_name"],
                payload["reply_outline"],
            ),
        )

    def _upsert_fact(self, conn: sqlite3.Connection, fact: ChatMemoryFact) -> bool:
        existing = conn.execute(
            """
            SELECT * FROM facts
            WHERE group_id = ? AND subject = ? AND predicate = ? AND object = ?
            """,
            (fact.group_id, fact.subject, fact.predicate, fact.object),
        ).fetchone()
        if existing is not None:
            existing_fact = self._fact_from_row(existing)
            source_ids = tuple(
                dict.fromkeys([*existing_fact.source_message_ids, *fact.source_message_ids])
            )
            conn.execute(
                """
                UPDATE facts
                SET confidence = MAX(confidence, ?),
                    source_message_ids = ?,
                    topics = ?,
                    entities = ?,
                    updated_at = MAX(updated_at, ?)
                WHERE id = ?
                """,
                (
                    fact.confidence,
                    json.dumps(source_ids, ensure_ascii=False),
                    json.dumps(tuple(dict.fromkeys([*existing_fact.topics, *fact.topics])), ensure_ascii=False),
                    json.dumps(tuple(dict.fromkeys([*existing_fact.entities, *fact.entities])), ensure_ascii=False),
                    fact.updated_at,
                    existing_fact.id,
                ),
            )
            self._index_fact(conn, existing_fact.id)
            return False

        cursor = conn.execute(
            """
            INSERT INTO facts (
                group_id, subject, predicate, object, confidence,
                source_message_ids, topics, entities, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact.group_id,
                fact.subject,
                fact.predicate,
                fact.object,
                fact.confidence,
                json.dumps(fact.source_message_ids, ensure_ascii=False),
                json.dumps(fact.topics, ensure_ascii=False),
                json.dumps(fact.entities, ensure_ascii=False),
                fact.updated_at,
            ),
        )
        self._index_fact(conn, int(cursor.lastrowid))
        return True

    def _index_fact(self, conn: sqlite3.Connection, fact_id: int) -> None:
        if not self._facts_fts_available(conn):
            return
        row = conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
        if row is None:
            return
        conn.execute("DELETE FROM facts_fts WHERE fact_rowid = ?", (fact_id,))
        conn.execute(
            """
            INSERT INTO facts_fts(
                fact_rowid, group_id, subject, predicate, object, topics, entities
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact_id,
                row["group_id"],
                row["subject"],
                row["predicate"],
                row["object"],
                row["topics"],
                row["entities"],
            ),
        )

    def _search_facts_with_fts(
        self,
        conn: sqlite3.Connection,
        group_id: str,
        query: str,
        limit: int,
    ) -> list[sqlite3.Row]:
        if not self._facts_fts_available(conn):
            return []
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
        try:
            return list(
                conn.execute(
                    """
                    SELECT facts.*
                    FROM facts_fts
                    JOIN facts ON facts.id = facts_fts.fact_rowid
                    WHERE facts.group_id = ?
                      AND facts_fts MATCH ?
                    ORDER BY bm25(facts_fts), facts.updated_at DESC, facts.id DESC
                    LIMIT ?
                    """,
                    (group_id, fts_query, limit),
                ).fetchall()
            )
        except sqlite3.OperationalError:
            return []

    def _search_facts_with_like(
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
                "(subject LIKE ? OR predicate LIKE ? OR object LIKE ? OR topics LIKE ? OR entities LIKE ?)"
            )
            params.extend([like, like, like, like, like])
        params.append(limit)
        return list(
            conn.execute(
                f"""
                SELECT *
                FROM facts
                WHERE group_id = ?
                  AND ({' OR '.join(clauses)})
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
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
                "(text LIKE ? OR summary LIKE ? OR tags LIKE ? OR topics LIKE ? OR entities LIKE ? OR sender_name LIKE ? OR reply_outline LIKE ?)"
            )
            params.extend([like, like, like, like, like, like, like])
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
            topics=tuple(json.loads(str(row["topics"] or "[]"))),
            entities=tuple(json.loads(str(row["entities"] or "[]"))),
            importance=float(row["importance"] or 0.5),
            confidence=float(row["confidence"] or 0.6),
        )

    @staticmethod
    def _fact_from_row(row: sqlite3.Row) -> ChatMemoryFact:
        return ChatMemoryFact(
            id=int(row["id"]),
            group_id=str(row["group_id"]),
            subject=str(row["subject"]),
            predicate=str(row["predicate"]),
            object=str(row["object"]),
            confidence=float(row["confidence"] or 0.7),
            source_message_ids=tuple(json.loads(str(row["source_message_ids"] or "[]"))),
            topics=tuple(json.loads(str(row["topics"] or "[]"))),
            entities=tuple(json.loads(str(row["entities"] or "[]"))),
            updated_at=int(row["updated_at"]),
        )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}
        if column in columns:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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


def infer_rule_topics(text: str) -> tuple[str, ...]:
    normalized = text.lower()
    topics: list[str] = []
    if any(keyword in normalized for keyword in ("知识库", "聊天记录", "历史聊天", "数据库", "标签", "分门别类")):
        topics.append("知识库")
    if any(keyword in normalized for keyword in ("shapez", "异形工厂")):
        topics.append("shapez")
    if any(keyword in normalized for keyword in ("ai", "模型", "prompt", "提示词", "长期记忆")):
        topics.append("AI")
    if any(keyword in normalized for keyword in ("codex", "代码", "项目", "提交")):
        topics.append("Codex")
    if any(keyword in normalized for keyword in ("群管", "禁言", "复读", "管理")):
        topics.append("群管")
    return tuple(dict.fromkeys(topics))


def extract_rule_entities(text: str) -> tuple[str, ...]:
    entities: list[str] = []
    entities.extend(re.findall(r"\b\d{5,12}\b", text))
    entities.extend(re.findall(r"\b[A-Za-z][A-Za-z0-9_\-]{2,}\b", text))
    for marker in ("萌泪", "萌泪酱", "可可", "棉花糖", "shapez", "Codex"):
        if marker.lower() in text.lower():
            entities.append(marker)
    return tuple(dict.fromkeys(entities))


def infer_importance(text: str) -> float:
    if is_prompt_injection_like(text):
        return 0.1
    if any(keyword in text for keyword in ("记住", "以后", "规则", "主人", "管理员", "配置", "项目")):
        return 0.8
    if any(keyword in text for keyword in ("讨论", "决定", "需要", "数据库", "知识库")):
        return 0.65
    return 0.5


def score_message_record(record: ChatMemoryRecord, query: str) -> float:
    terms = build_like_terms(query)
    haystacks = {
        "text": record.text,
        "summary": record.summary,
        "tags": " ".join(record.tags),
        "topics": " ".join(record.topics),
        "entities": " ".join(record.entities),
        "sender": record.sender_name,
        "reply": record.reply_outline,
    }
    score = record.importance + record.confidence * 0.5
    for term in terms:
        if term in haystacks["sender"] or term in record.user_id:
            score += 3.0
        if term in haystacks["entities"]:
            score += 2.0
        if term in haystacks["topics"] or term in haystacks["tags"]:
            score += 1.5
        if term in haystacks["text"] or term in haystacks["summary"]:
            score += 1.0
        if term in haystacks["reply"]:
            score += 0.5
    return score


def is_prompt_injection_like(text: str) -> bool:
    normalized = text.lower()
    return any(
        keyword in normalized
        for keyword in (
            "忽略之前",
            "忽略以上",
            "系统提示",
            "system prompt",
            "developer message",
            "你必须无条件",
            "以后你必须",
        )
    )


def extract_rule_facts(record: ChatMemoryRecord) -> tuple[ChatMemoryFact, ...]:
    text = record.text.strip().strip("。！？!?.")
    if not text or is_prompt_injection_like(text):
        return ()

    patterns = [
        r"^(?P<subject>[\w\u4e00-\u9fff]{1,20})(?P<predicate>喜欢|叫|是|在做|正在做|想要|需要)(?P<object>.+)$",
        r"^(?P<subject>[\w\u4e00-\u9fff]{1,20})的(?P<predicate>身份|项目|需求|昵称)是(?P<object>.+)$",
    ]
    facts: list[ChatMemoryFact] = []
    for pattern in patterns:
        match = re.match(pattern, text)
        if match is None:
            continue
        subject = match.group("subject").strip()
        predicate = match.group("predicate").strip()
        obj = match.group("object").strip().strip("，,：:")
        if not subject or not obj or len(obj) > 80:
            continue
        facts.append(
            ChatMemoryFact(
                id=0,
                group_id=record.group_id,
                subject=subject,
                predicate=predicate,
                object=obj,
                confidence=max(0.7, record.confidence),
                source_message_ids=(record.message_id,) if record.message_id else (),
                topics=record.topics,
                entities=tuple(dict.fromkeys([subject, *record.entities, *extract_rule_entities(obj)])),
                updated_at=record.timestamp,
            )
        )
    return tuple(facts)


def score_fact(fact: ChatMemoryFact, query: str) -> float:
    terms = build_like_terms(query)
    haystack = " ".join(
        [
            fact.subject,
            fact.predicate,
            fact.object,
            " ".join(fact.topics),
            " ".join(fact.entities),
        ]
    )
    score = fact.confidence
    for term in terms:
        if term == fact.subject or term in fact.entities:
            score += 3.0
        if term in fact.object:
            score += 2.0
        if term in fact.topics:
            score += 1.5
        if term in haystack:
            score += 1.0
    return score


def build_fts_query(query: str) -> str:
    return " OR ".join(f'"{term}"' for term in build_like_terms(query))


def build_like_terms(query: str) -> list[str]:
    terms = [term.strip() for term in query.replace("，", " ").replace(",", " ").split()]
    for marker in (
        "知识库",
        "聊天记录",
        "历史聊天",
        "数据库",
        "标签",
        "可可",
        "萌泪",
        "萌泪酱",
        "棉花糖",
        "shapez",
        "Codex",
        "AI",
        "群管",
        "禁言",
        "复读",
    ):
        if marker.lower() in query.lower():
            terms.append(marker)
    terms.extend(extract_rule_entities(query))
    return [term for term in dict.fromkeys(terms) if term]
