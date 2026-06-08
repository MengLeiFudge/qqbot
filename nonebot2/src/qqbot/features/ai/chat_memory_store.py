from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
import time

from qqbot.features.ai.gateway import is_safety_rejection_text
from qqbot.features.ai.output_style import sanitize_ai_output_text
from qqbot.services.group_nick_store import GroupNickStore


VALID_DIRECTIONS = {"incoming", "bot"}
MUTUALLY_EXCLUSIVE_FACT_PREDICATES = {
    "叫",
    "不喜欢",
    "身份",
    "项目",
    "需求",
    "昵称",
    "主人",
    "规则",
}
PROTECTED_FACT_SUBJECTS = {
    "bot",
    "机器人",
    "棉花糖",
    "萌萌棉花糖",
    "萌萌棉花糖♪",
}
PROTECTED_FACT_OBJECT_KEYWORDS = (
    "主人",
    "管理员",
    "bot管理员",
    "Bot 管理员",
    "系统提示",
    "开发者",
)
PROTECTED_FACT_PREDICATES = {
    "身份",
    "是",
}
PROTECTED_FACT_RELATION_OBJECTS = {
    "你",
    "bot",
    "机器人",
    "萌萌棉花糖",
    "萌萌棉花糖♪",
}
GROUP_VISIBLE_PRIVATE_PROFILE_PREDICATES = {
    "昵称",
    "身份",
    "喜欢",
    "不喜欢",
    "行为指令",
}
TRUST_LEVEL_WEIGHT = {"chat": 0.0, "bot": 1.5, "admin": 3.0, "system": 4.0}
SOURCE_TYPE_WEIGHT = {"user": 0.0, "bot": 0.8, "admin": 2.0, "system": 2.5}
STATUS_WEIGHT = {"active": 0.0, "superseded": -8.0}
BEHAVIOR_INSTRUCTION_SHORT_TTL_SECONDS = 60 * 60 * 2


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
    space_id: str = ""
    actor_id: str = ""
    visibility: str = "group_public"
    memory_type: str = "raw_message"


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
    source_type: str = "user"
    trust_level: str = "chat"
    status: str = "active"
    space_id: str = ""
    visibility: str = "group_public"
    memory_type: str = "fact"


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
        space_id: str | None = None,
        actor_id: str | None = None,
        visibility: str | None = None,
        memory_type: str = "raw_message",
        has_image: bool = False,
        has_at: bool = False,
        reply_message_id: int | str | None = None,
        reply_user_id: int | str | None = None,
        reply_outline: str = "",
    ) -> bool:
        normalized_text = sanitize_ai_output_text(text) if direction == "bot" else text.strip()
        if not normalized_text or is_safety_rejection_text(normalized_text):
            return False
        if direction == "bot" and is_sensitive_memory_claim_text(normalized_text):
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
            "space_id": space_id or build_group_space_id(group_id),
            "message_id": str(message_id or ""),
            "direction": direction,
            "user_id": str(user_id),
            "actor_id": actor_id or build_user_actor_id(user_id),
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
            "visibility": visibility or ("group_public" if str(group_id).isdigit() else "private"),
            "memory_type": memory_type,
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
                    group_id, space_id, message_id, direction, user_id, actor_id, sender_name,
                    text, summary, tags, topics, entities, importance, confidence,
                    timestamp, has_image, has_at, visibility, memory_type,
                    reply_message_id, reply_user_id, reply_outline
                )
                VALUES (
                    :group_id, :space_id, :message_id, :direction, :user_id, :actor_id, :sender_name,
                    :text, :summary, :tags, :topics, :entities, :importance, :confidence,
                    :timestamp, :has_image, :has_at, :visibility, :memory_type,
                    :reply_message_id, :reply_user_id, :reply_outline
                )
                """,
                payload,
            )
            row_id = int(cursor.lastrowid)
            if self._fts_available(conn):
                self._index_fts(conn, row_id, payload)
            self._extract_facts_from_record(conn, self._record_from_row_by_id(conn, row_id))
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
        expanded_query = self._expand_search_query(group_id, normalized_query)

        with self._connect() as conn:
            self._ensure_schema(conn)
            search_limit = max(limit * 4, limit)
            rows = self._search_with_fts(conn, str(group_id), expanded_query, search_limit)
            if len(rows) < limit:
                seen_ids = {int(row["id"]) for row in rows}
                rows.extend(
                    row
                    for row in self._search_with_like(
                        conn,
                        str(group_id),
                        expanded_query,
                        search_limit,
                    )
                    if int(row["id"]) not in seen_ids
                )
        records = tuple(
            record
            for _, record in sorted(
                (
                    (
                        score_message_record(self._record_from_row(row), expanded_query),
                        self._record_from_row(row),
                    )
                    for row in rows
                ),
                key=lambda item: (-item[0], -item[1].timestamp, -item[1].id),
            )[:limit]
        )
        return records

    def search_user_messages(
        self,
        *,
        current_group_id: int | str,
        user_id: int | str,
        query: str,
        limit: int = 4,
    ) -> tuple[ChatMemoryRecord, ...]:
        normalized_query = query.strip()
        normalized_user_id = str(user_id).strip()
        if not normalized_query or not normalized_user_id or limit <= 0 or not self.db_path.exists():
            return ()
        expanded_query = self._expand_search_query(current_group_id, normalized_query)

        with self._connect() as conn:
            self._ensure_schema(conn)
            search_limit = max(limit * 4, limit)
            rows = self._search_user_messages_with_fts(
                conn,
                str(current_group_id),
                normalized_user_id,
                expanded_query,
                search_limit,
            )
            if len(rows) < limit:
                seen_ids = {int(row["id"]) for row in rows}
                rows.extend(
                    row
                    for row in self._search_user_messages_with_like(
                        conn,
                        str(current_group_id),
                        normalized_user_id,
                        expanded_query,
                        search_limit,
                    )
                    if int(row["id"]) not in seen_ids
                )
        records = tuple(
            record
            for _, record in sorted(
                (
                    (
                        score_message_record(self._record_from_row(row), expanded_query),
                        self._record_from_row(row),
                    )
                    for row in rows
                ),
                key=lambda item: (-item[0], -item[1].timestamp, -item[1].id),
            )[:limit]
        )
        return records

    def load_recent_user_messages_across_groups(
        self,
        *,
        current_group_id: int | str,
        user_id: int | str,
        limit: int = 4,
    ) -> tuple[ChatMemoryRecord, ...]:
        normalized_user_id = str(user_id).strip()
        if not normalized_user_id or limit <= 0 or not self.db_path.exists():
            return ()
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE actor_id = ?
                  AND space_id != ?
                  AND direction = 'incoming'
                  AND visibility = 'group_public'
                  AND text != ''
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (build_user_actor_id(normalized_user_id), build_group_space_id(current_group_id), limit),
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def load_recent_group_user_messages(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        limit: int = 100,
    ) -> tuple[ChatMemoryRecord, ...]:
        normalized_group_id = str(group_id).strip()
        normalized_user_id = str(user_id).strip()
        if (
            not normalized_group_id
            or not normalized_user_id
            or limit <= 0
            or not self.db_path.exists()
        ):
            return ()
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE group_id = ?
                  AND user_id = ?
                  AND direction = 'incoming'
                  AND visibility = 'group_public'
                  AND text != ''
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (normalized_group_id, normalized_user_id, limit),
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def load_recent_actor_messages_across_spaces(
        self,
        *,
        actor_id: str,
        exclude_space_id: str,
        visibility: str = "group_public",
        limit: int = 4,
    ) -> tuple[ChatMemoryRecord, ...]:
        normalized_actor_id = actor_id.strip()
        if not normalized_actor_id or limit <= 0 or not self.db_path.exists():
            return ()
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE actor_id = ?
                  AND space_id != ?
                  AND direction = 'incoming'
                  AND visibility = ?
                  AND text != ''
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (normalized_actor_id, exclude_space_id, visibility, limit),
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def load_recent_space_messages(
        self,
        *,
        space_id: str,
        visibility: str,
        limit: int = 100,
    ) -> tuple[ChatMemoryRecord, ...]:
        if not space_id.strip() or limit <= 0 or not self.db_path.exists():
            return ()
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE space_id = ?
                  AND visibility = ?
                  AND text != ''
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (space_id, visibility, limit),
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def search_space_messages(
        self,
        *,
        space_id: str,
        query: str,
        visibility: str,
        limit: int = 6,
    ) -> tuple[ChatMemoryRecord, ...]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0 or not self.db_path.exists():
            return ()
        terms = build_like_terms(normalized_query)
        if not terms:
            return ()
        clauses: list[str] = []
        params: list[object] = [space_id, visibility]
        for term in terms:
            like = f"%{term}%"
            clauses.append(
                "(text LIKE ? OR summary LIKE ? OR tags LIKE ? OR topics LIKE ? OR entities LIKE ? OR sender_name LIKE ? OR reply_outline LIKE ?)"
            )
            params.extend([like, like, like, like, like, like, like])
        params.append(max(limit * 4, limit))
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                f"""
                SELECT *
                FROM messages
                WHERE space_id = ?
                  AND visibility = ?
                  AND ({' OR '.join(clauses)})
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        records = tuple(
            record
            for _, record in sorted(
                (
                    (score_message_record(self._record_from_row(row), normalized_query), self._record_from_row(row))
                    for row in rows
                ),
                key=lambda item: (-item[0], -item[1].timestamp, -item[1].id),
            )[:limit]
        )
        return records

    def load_messages_by_message_ids(
        self,
        group_id: int | str,
        message_ids: tuple[str, ...] | list[str],
    ) -> tuple[ChatMemoryRecord, ...]:
        normalized_ids = tuple(dict.fromkeys(str(message_id) for message_id in message_ids if str(message_id)))
        if not normalized_ids or not self.db_path.exists():
            return ()
        placeholders = ",".join("?" for _ in normalized_ids)
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                f"""
                SELECT *
                FROM messages
                WHERE group_id = ?
                  AND message_id IN ({placeholders})
                ORDER BY timestamp DESC, id DESC
                """,
                (str(group_id), *normalized_ids),
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

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
                inserted += self._extract_facts_from_record(conn, self._record_from_row(row))
            return inserted

    def rebuild_facts(self, group_id: int | str) -> dict[str, int]:
        normalized_group_id = str(group_id)
        with self._connect() as conn:
            self._ensure_schema(conn)
            message_rows = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE group_id = ?
                ORDER BY timestamp ASC, id ASC
                """,
                (normalized_group_id,),
            ).fetchall()
            removable_rows = conn.execute(
                """
                SELECT *
                FROM facts
                WHERE group_id = ?
                  AND trust_level = 'chat'
                """,
                (normalized_group_id,),
            ).fetchall()
            disabled_facts = [self._fact_from_row(row) for row in removable_rows if row["status"] == "disabled"]
            removable_ids = [int(row["id"]) for row in removable_rows]
            if removable_ids:
                placeholders = ",".join("?" for _ in removable_ids)
                conn.execute(f"DELETE FROM facts WHERE id IN ({placeholders})", removable_ids)
                if self._facts_fts_available(conn):
                    conn.execute(
                        f"DELETE FROM facts_fts WHERE fact_rowid IN ({placeholders})",
                        removable_ids,
                    )
            inserted = 0
            for row in message_rows:
                inserted += self._extract_facts_from_record(conn, self._record_from_row(row))
            disabled_restored = 0
            for fact in disabled_facts:
                if self._restore_disabled_fact(conn, fact):
                    disabled_restored += 1
            return {
                "messages_scanned": len(message_rows),
                "facts_removed": len(removable_ids),
                "facts_inserted": inserted,
                "disabled_facts_restored": disabled_restored,
            }

    def debug_search(
        self,
        group_id: int | str,
        query: str,
        *,
        limit: int = 6,
    ) -> dict[str, object]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0:
            return {
                "group_id": str(group_id),
                "query": normalized_query,
                "expanded_query": "",
                "facts": [],
                "messages": [],
            }
        expanded_query = self._expand_search_query(group_id, normalized_query)
        facts = self.search_facts(group_id, normalized_query, limit=limit)
        records = self.search_messages(group_id, normalized_query, limit=limit)
        return {
            "group_id": str(group_id),
            "query": normalized_query,
            "expanded_query": expanded_query,
            "facts": [
                self._fact_debug_payload(
                    fact,
                    expanded_query,
                    self.load_messages_by_message_ids(group_id, fact.source_message_ids),
                )
                for fact in facts
            ],
            "messages": [
                self._record_debug_payload(record, expanded_query)
                for record in records
            ],
        }

    def upsert_trusted_fact(
        self,
        *,
        group_id: int | str,
        subject: str,
        predicate: str,
        object: str,
        confidence: float = 1.0,
        source_type: str = "system",
        trust_level: str = "system",
        topics: tuple[str, ...] | list[str] = (),
        entities: tuple[str, ...] | list[str] = (),
        updated_at: int = 0,
    ) -> ChatMemoryFact:
        fact = ChatMemoryFact(
            id=0,
            group_id=str(group_id),
            subject=subject.strip(),
            predicate=predicate.strip(),
            object=object.strip(),
            confidence=float(confidence),
            source_message_ids=(),
            topics=tuple(dict.fromkeys(str(item).strip() for item in topics if str(item).strip())),
            entities=tuple(dict.fromkeys(str(item).strip() for item in entities if str(item).strip())),
            updated_at=int(updated_at),
            source_type=source_type,
            trust_level=trust_level,
            status="active",
            space_id=build_group_space_id(group_id),
            visibility="group_public",
            memory_type="fact",
        )
        if not fact.subject or not fact.predicate or not fact.object:
            raise ValueError("Fact subject, predicate and object are required.")
        with self._connect() as conn:
            self._ensure_schema(conn)
            self._upsert_fact(conn, fact)
            row = conn.execute(
                """
                SELECT *
                FROM facts
                WHERE group_id = ?
                  AND subject = ?
                  AND predicate = ?
                  AND object = ?
                """,
                (fact.group_id, fact.subject, fact.predicate, fact.object),
            ).fetchone()
            if row is None:
                raise ValueError("Trusted fact was rejected.")
            return self._fact_from_row(row)

    def upsert_memory_summary(
        self,
        *,
        group_id: int | str,
        topic: str,
        summary: str,
        source_message_ids: tuple[str, ...],
        updated_at: int,
    ) -> bool:
        fact = ChatMemoryFact(
            id=0,
            group_id=str(group_id),
            subject="群主题摘要",
            predicate="摘要",
            object=summary.strip(),
            confidence=0.75,
            source_message_ids=tuple(dict.fromkeys(source_message_ids)),
            topics=(topic.strip(), "主题摘要"),
            entities=("群主题摘要", topic.strip()),
            updated_at=int(updated_at),
            source_type="system",
            trust_level="system",
            status="active",
            space_id=build_group_space_id(group_id),
            visibility="group_public",
            memory_type="summary",
        )
        if not fact.object or not topic.strip():
            return False
        with self._connect() as conn:
            self._ensure_schema(conn)
            return self._upsert_fact(conn, fact)

    def set_fact_status(self, fact_id: int, status: str) -> bool:
        normalized_status = status.strip()
        if normalized_status not in {"active", "disabled", "superseded"}:
            raise ValueError(f"Unsupported fact status: {status}")
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute("SELECT id FROM facts WHERE id = ?", (int(fact_id),)).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE facts SET status = ? WHERE id = ?",
                (normalized_status, int(fact_id)),
            )
            self._index_fact(conn, int(fact_id))
            return True

    def search_facts(
        self,
        group_id: int | str,
        query: str,
        *,
        limit: int = 6,
        now: int | float | None = None,
    ) -> tuple[ChatMemoryFact, ...]:
        normalized_query = query.strip()
        if not normalized_query or limit <= 0 or not self.db_path.exists():
            return ()
        expanded_query = self._expand_search_query(group_id, normalized_query)
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = self._search_facts_with_fts(conn, str(group_id), expanded_query, limit * 4)
            if len(rows) < limit:
                seen_ids = {int(row["id"]) for row in rows}
                rows.extend(
                    row
                    for row in self._search_facts_with_like(
                        conn,
                        str(group_id),
                        expanded_query,
                        limit * 4,
                    )
                    if int(row["id"]) not in seen_ids
                )
        active_fact_list: list[ChatMemoryFact] = []
        for row in rows:
            fact = self._fact_from_row(row)
            if is_behavior_instruction_active(fact, now=now):
                active_fact_list.append(fact)
        facts = tuple(
            fact
            for _, fact in sorted(
                ((score_fact(fact, expanded_query), fact) for fact in active_fact_list),
                key=lambda item: (-item[0], -item[1].updated_at, -item[1].id),
            )[:limit]
        )
        return facts

    def search_user_facts(
        self,
        *,
        current_group_id: int | str,
        user_id: int | str,
        aliases: tuple[str, ...] | list[str],
        query: str,
        limit: int = 4,
    ) -> tuple[ChatMemoryFact, ...]:
        normalized_query = query.strip()
        identity_terms = tuple(
            dict.fromkeys(
                term.strip()
                for term in (str(user_id), *aliases)
                if term and term.strip()
            )
        )
        if not normalized_query or not identity_terms or limit <= 0 or not self.db_path.exists():
            return ()
        expanded_query = self._expand_search_query(current_group_id, normalized_query)
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = self._search_user_facts_with_like(
                conn,
                str(current_group_id),
                identity_terms,
                expanded_query,
                limit * 4,
            )
        active_fact_list: list[ChatMemoryFact] = []
        for row in rows:
            fact = self._fact_from_row(row)
            if is_behavior_instruction_active(fact) and is_group_visible_user_profile_fact(fact):
                active_fact_list.append(fact)
        facts = tuple(
            fact
            for _, fact in sorted(
                ((score_fact(fact, expanded_query), fact) for fact in active_fact_list),
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

    def _expand_search_query(self, group_id: int | str, query: str) -> str:
        terms = list(build_like_terms(query))
        try:
            nick_store = GroupNickStore(self.data_root / "settings" / "group_nick.json")
            if str(group_id).isdigit():
                terms.extend(nick_store.build_alias_terms(group_id, query))
        except Exception:
            pass
        return " ".join(dict.fromkeys([query, *terms]))

    def _fact_debug_payload(
        self,
        fact: ChatMemoryFact,
        query: str,
        source_records: tuple[ChatMemoryRecord, ...],
    ) -> dict[str, object]:
        return {
            "id": fact.id,
            "group_id": fact.group_id,
            "space_id": fact.space_id,
            "subject": fact.subject,
            "predicate": fact.predicate,
            "object": fact.object,
            "confidence": fact.confidence,
            "source_message_ids": list(fact.source_message_ids),
            "topics": list(fact.topics),
            "entities": list(fact.entities),
            "updated_at": fact.updated_at,
            "source_type": fact.source_type,
            "trust_level": fact.trust_level,
            "status": fact.status,
            "visibility": fact.visibility,
            "memory_type": fact.memory_type,
            "score": score_fact(fact, query),
            "source_records": [
                self._record_debug_payload(record, query)
                for record in source_records
            ],
        }

    def _record_debug_payload(
        self,
        record: ChatMemoryRecord,
        query: str,
    ) -> dict[str, object]:
        return {
            "id": record.id,
            "group_id": record.group_id,
            "space_id": record.space_id,
            "message_id": record.message_id,
            "direction": record.direction,
            "user_id": record.user_id,
            "actor_id": record.actor_id,
            "sender_name": record.sender_name,
            "text": record.text,
            "summary": record.summary,
            "tags": list(record.tags),
            "topics": list(record.topics),
            "entities": list(record.entities),
            "timestamp": record.timestamp,
            "visibility": record.visibility,
            "memory_type": record.memory_type,
            "score": score_message_record(record, query),
        }

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                space_id TEXT NOT NULL DEFAULT '',
                message_id TEXT NOT NULL DEFAULT '',
                direction TEXT NOT NULL,
                user_id TEXT NOT NULL,
                actor_id TEXT NOT NULL DEFAULT '',
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
                visibility TEXT NOT NULL DEFAULT 'group_public',
                memory_type TEXT NOT NULL DEFAULT 'raw_message',
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
        self._ensure_column(conn, "messages", "space_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "messages", "actor_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "messages", "visibility", "TEXT NOT NULL DEFAULT 'group_public'")
        self._ensure_column(conn, "messages", "memory_type", "TEXT NOT NULL DEFAULT 'raw_message'")
        conn.execute(
            "UPDATE messages SET space_id = 'qq:group:' || group_id WHERE space_id = ''"
        )
        conn.execute(
            "UPDATE messages SET actor_id = 'qq:user:' || user_id WHERE actor_id = ''"
        )
        conn.execute(
            "UPDATE messages SET visibility = 'group_public' WHERE visibility = ''"
        )
        conn.execute(
            "UPDATE messages SET memory_type = 'raw_message' WHERE memory_type = ''"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_space_time ON messages(space_id, timestamp DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_actor_space ON messages(actor_id, space_id, timestamp DESC)")
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
                updated_at INTEGER NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'user',
                trust_level TEXT NOT NULL DEFAULT 'chat',
                status TEXT NOT NULL DEFAULT 'active',
                space_id TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'group_public',
                memory_type TEXT NOT NULL DEFAULT 'fact'
            )
            """
        )
        self._ensure_column(conn, "facts", "source_type", "TEXT NOT NULL DEFAULT 'user'")
        self._ensure_column(conn, "facts", "trust_level", "TEXT NOT NULL DEFAULT 'chat'")
        self._ensure_column(conn, "facts", "status", "TEXT NOT NULL DEFAULT 'active'")
        self._ensure_column(conn, "facts", "space_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "facts", "visibility", "TEXT NOT NULL DEFAULT 'group_public'")
        self._ensure_column(conn, "facts", "memory_type", "TEXT NOT NULL DEFAULT 'fact'")
        conn.execute(
            "UPDATE facts SET space_id = 'qq:group:' || group_id WHERE space_id = ''"
        )
        conn.execute(
            "UPDATE facts SET visibility = 'group_public' WHERE visibility = ''"
        )
        conn.execute(
            "UPDATE facts SET memory_type = 'fact' WHERE memory_type = ''"
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
        self._ensure_messages_fts_schema(conn)
        self._ensure_facts_fts_schema(conn)

    def _ensure_messages_fts_schema(self, conn: sqlite3.Connection) -> None:
        if not self._fts_available(conn):
            return
        expected = {
            "message_rowid",
            "text",
            "summary",
            "tags",
            "topics",
            "entities",
            "sender_name",
            "reply_outline",
        }
        columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(messages_fts)")}
        if expected.issubset(columns):
            return
        conn.execute("DROP TABLE messages_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE messages_fts USING fts5(
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
        for row in conn.execute("SELECT * FROM messages").fetchall():
            record = self._record_from_row(row)
            self._index_fts(conn, record.id, self._payload_from_record(record))

    def _ensure_facts_fts_schema(self, conn: sqlite3.Connection) -> None:
        if not self._facts_fts_available(conn):
            return
        expected = {"fact_rowid", "group_id", "subject", "predicate", "object", "topics", "entities"}
        columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(facts_fts)")}
        if expected.issubset(columns):
            return
        conn.execute("DROP TABLE facts_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE facts_fts USING fts5(
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
        for row in conn.execute("SELECT id FROM facts").fetchall():
            self._index_fact(conn, int(row["id"]))

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
        if is_protected_chat_fact(fact):
            return False
        existing = conn.execute(
            """
            SELECT * FROM facts
            WHERE group_id = ? AND subject = ? AND predicate = ? AND object = ?
            """,
            (fact.group_id, fact.subject, fact.predicate, fact.object),
        ).fetchone()
        if existing is not None:
            existing_fact = self._fact_from_row(existing)
            if is_stronger_fact(existing_fact, fact) and existing_fact.object != fact.object:
                return False
            if is_mutually_exclusive_fact(fact):
                stronger_conflict = self._find_stronger_conflicting_fact(conn, fact)
                if stronger_conflict is not None:
                    self._merge_fact_sources(conn, existing_fact, fact, status="superseded")
                    return False
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
                    updated_at = MAX(updated_at, ?),
                    source_type = ?,
                    trust_level = ?,
                    status = 'active',
                    space_id = ?,
                    visibility = ?,
                    memory_type = ?
                WHERE id = ?
                """,
                (
                    fact.confidence,
                    json.dumps(source_ids, ensure_ascii=False),
                    json.dumps(tuple(dict.fromkeys([*existing_fact.topics, *fact.topics])), ensure_ascii=False),
                    json.dumps(tuple(dict.fromkeys([*existing_fact.entities, *fact.entities])), ensure_ascii=False),
                    fact.updated_at,
                    strongest_source_type(existing_fact.source_type, fact.source_type),
                    strongest_trust_level(existing_fact.trust_level, fact.trust_level),
                    fact.space_id or existing_fact.space_id or build_group_space_id(fact.group_id),
                    fact.visibility or existing_fact.visibility,
                    fact.memory_type or existing_fact.memory_type,
                    existing_fact.id,
                ),
            )
            self._index_fact(conn, existing_fact.id)
            return False

        if not self._supersede_conflicting_facts(conn, fact):
            return False
        cursor = conn.execute(
            """
            INSERT INTO facts (
                group_id, subject, predicate, object, confidence,
                source_message_ids, topics, entities, updated_at,
                source_type, trust_level, status, space_id, visibility, memory_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                fact.source_type,
                fact.trust_level,
                fact.status,
                fact.space_id or build_group_space_id(fact.group_id),
                fact.visibility,
                fact.memory_type,
            ),
        )
        self._index_fact(conn, int(cursor.lastrowid))
        return True

    def _merge_fact_sources(
        self,
        conn: sqlite3.Connection,
        existing_fact: ChatMemoryFact,
        fact: ChatMemoryFact,
        *,
        status: str,
    ) -> None:
        source_ids = tuple(dict.fromkeys([*existing_fact.source_message_ids, *fact.source_message_ids]))
        conn.execute(
            """
            UPDATE facts
            SET confidence = MAX(confidence, ?),
                source_message_ids = ?,
                topics = ?,
                entities = ?,
                updated_at = MAX(updated_at, ?),
                source_type = ?,
                trust_level = ?,
                status = ?,
                space_id = ?,
                visibility = ?,
                memory_type = ?
            WHERE id = ?
            """,
            (
                fact.confidence,
                json.dumps(source_ids, ensure_ascii=False),
                json.dumps(tuple(dict.fromkeys([*existing_fact.topics, *fact.topics])), ensure_ascii=False),
                json.dumps(tuple(dict.fromkeys([*existing_fact.entities, *fact.entities])), ensure_ascii=False),
                fact.updated_at,
                strongest_source_type(existing_fact.source_type, fact.source_type),
                strongest_trust_level(existing_fact.trust_level, fact.trust_level),
                status,
                fact.space_id or existing_fact.space_id or build_group_space_id(fact.group_id),
                fact.visibility or existing_fact.visibility,
                fact.memory_type or existing_fact.memory_type,
                existing_fact.id,
            ),
        )
        self._index_fact(conn, existing_fact.id)

    def _supersede_conflicting_facts(
        self,
        conn: sqlite3.Connection,
        fact: ChatMemoryFact,
    ) -> bool:
        if not is_mutually_exclusive_fact(fact):
            return True
        rows = conn.execute(
            """
            SELECT *
            FROM facts
            WHERE group_id = ?
              AND subject = ?
              AND predicate = ?
              AND object != ?
              AND status = 'active'
            """,
            (fact.group_id, fact.subject, fact.predicate, fact.object),
        ).fetchall()
        superseded_ids: list[int] = []
        for row in rows:
            existing_fact = self._fact_from_row(row)
            if not is_behavior_instruction_active(existing_fact):
                continue
            if is_stronger_fact(existing_fact, fact):
                return False
            superseded_ids.append(existing_fact.id)
        if not superseded_ids:
            return True
        placeholders = ",".join("?" for _ in superseded_ids)
        conn.execute(
            f"UPDATE facts SET status = 'superseded' WHERE id IN ({placeholders})",
            superseded_ids,
        )
        for fact_id in superseded_ids:
            self._index_fact(conn, fact_id)
        return True

    def _find_stronger_conflicting_fact(
        self,
        conn: sqlite3.Connection,
        fact: ChatMemoryFact,
    ) -> ChatMemoryFact | None:
        if not is_mutually_exclusive_fact(fact):
            return None
        rows = conn.execute(
            """
            SELECT *
            FROM facts
            WHERE group_id = ?
              AND subject = ?
              AND predicate = ?
              AND object != ?
              AND status = 'active'
            """,
            (fact.group_id, fact.subject, fact.predicate, fact.object),
        ).fetchall()
        for row in rows:
            existing_fact = self._fact_from_row(row)
            if not is_behavior_instruction_active(existing_fact):
                continue
            if is_stronger_fact(existing_fact, fact):
                return existing_fact
        return None

    def _extract_facts_from_record(self, conn: sqlite3.Connection, record: ChatMemoryRecord) -> int:
        inserted = 0
        for fact in extract_rule_facts(record):
            if self._upsert_fact(conn, fact):
                inserted += 1
        return inserted

    def _restore_disabled_fact(self, conn: sqlite3.Connection, fact: ChatMemoryFact) -> bool:
        current = conn.execute(
            """
            SELECT *
            FROM facts
            WHERE group_id = ?
              AND subject = ?
              AND predicate = ?
              AND object = ?
            """,
            (fact.group_id, fact.subject, fact.predicate, fact.object),
        ).fetchone()
        if current is None:
            cursor = conn.execute(
                """
                INSERT INTO facts (
                    group_id, subject, predicate, object, confidence,
                    source_message_ids, topics, entities, updated_at,
                    source_type, trust_level, status, space_id, visibility, memory_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'disabled', ?, ?, ?)
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
                    fact.source_type,
                    fact.trust_level,
                    fact.space_id or build_group_space_id(fact.group_id),
                    fact.visibility,
                    fact.memory_type,
                ),
            )
            self._index_fact(conn, int(cursor.lastrowid))
            return True
        current_fact = self._fact_from_row(current)
        source_ids = tuple(dict.fromkeys([*current_fact.source_message_ids, *fact.source_message_ids]))
        conn.execute(
            """
            UPDATE facts
            SET confidence = MAX(confidence, ?),
                source_message_ids = ?,
                topics = ?,
                entities = ?,
                updated_at = MAX(updated_at, ?),
                source_type = ?,
                trust_level = ?,
                status = 'disabled',
                space_id = ?,
                visibility = ?,
                memory_type = ?
            WHERE id = ?
            """,
            (
                fact.confidence,
                json.dumps(source_ids, ensure_ascii=False),
                json.dumps(tuple(dict.fromkeys([*current_fact.topics, *fact.topics])), ensure_ascii=False),
                json.dumps(tuple(dict.fromkeys([*current_fact.entities, *fact.entities])), ensure_ascii=False),
                fact.updated_at,
                strongest_source_type(current_fact.source_type, fact.source_type),
                strongest_trust_level(current_fact.trust_level, fact.trust_level),
                fact.space_id or current_fact.space_id or build_group_space_id(fact.group_id),
                fact.visibility or current_fact.visibility,
                fact.memory_type or current_fact.memory_type,
                current_fact.id,
            ),
        )
        self._index_fact(conn, current_fact.id)
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
                      AND facts.status = 'active'
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
                  AND status = 'active'
                  AND ({' OR '.join(clauses)})
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        )

    def _search_user_facts_with_like(
        self,
        conn: sqlite3.Connection,
        current_group_id: str,
        identity_terms: tuple[str, ...],
        query: str,
        limit: int,
    ) -> list[sqlite3.Row]:
        query_terms = build_like_terms(query)
        if not query_terms:
            return []
        identity_clauses: list[str] = []
        params: list[object] = []
        for term in identity_terms:
            like = f"%{term}%"
            identity_clauses.append("(subject = ? OR entities LIKE ?)")
            params.extend([term, like])

        query_clauses: list[str] = []
        for term in query_terms:
            like = f"%{term}%"
            query_clauses.append(
                "(subject LIKE ? OR predicate LIKE ? OR object LIKE ? OR topics LIKE ? OR entities LIKE ?)"
            )
            params.extend([like, like, like, like, like])
        params.append(limit)
        return list(
            conn.execute(
                f"""
                SELECT *
                FROM facts
                WHERE status = 'active'
                  AND group_id != ?
                  AND subject != '群规则'
                  AND ({' OR '.join(identity_clauses)})
                  AND ({' OR '.join(query_clauses)})
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (current_group_id, *params),
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

    def _search_user_messages_with_fts(
        self,
        conn: sqlite3.Connection,
        current_group_id: str,
        user_id: str,
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
                    WHERE messages.user_id = ?
                      AND messages.group_id != ?
                      AND messages.visibility = 'group_public'
                      AND messages_fts MATCH ?
                    ORDER BY bm25(messages_fts), messages.timestamp DESC, messages.id DESC
                    LIMIT ?
                    """,
                    (user_id, current_group_id, fts_query, limit),
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

    def _search_user_messages_with_like(
        self,
        conn: sqlite3.Connection,
        current_group_id: str,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[sqlite3.Row]:
        terms = build_like_terms(query)
        if not terms:
            return []

        clauses: list[str] = []
        params: list[object] = [user_id, current_group_id]
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
                WHERE user_id = ?
                  AND group_id != ?
                  AND visibility = 'group_public'
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
            space_id=str(row["space_id"] or build_group_space_id(row["group_id"])),
            actor_id=str(row["actor_id"] or build_user_actor_id(row["user_id"])),
            visibility=str(row["visibility"] or "group_public"),
            memory_type=str(row["memory_type"] or "raw_message"),
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
            source_type=str(row["source_type"] or "user"),
            trust_level=str(row["trust_level"] or "chat"),
            status=str(row["status"] or "active"),
            space_id=str(row["space_id"] or build_group_space_id(row["group_id"])),
            visibility=str(row["visibility"] or "group_public"),
            memory_type=str(row["memory_type"] or "fact"),
        )

    def _record_from_row_by_id(self, conn: sqlite3.Connection, row_id: int) -> ChatMemoryRecord:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (row_id,)).fetchone()
        if row is None:
            raise ValueError(f"Message row not found: {row_id}")
        return self._record_from_row(row)

    @staticmethod
    def _payload_from_record(record: ChatMemoryRecord) -> dict[str, object]:
        return {
            "text": record.text,
            "summary": record.summary,
            "tags": json.dumps(record.tags, ensure_ascii=False),
            "topics": json.dumps(record.topics, ensure_ascii=False),
            "entities": json.dumps(record.entities, ensure_ascii=False),
            "sender_name": record.sender_name,
            "reply_outline": record.reply_outline,
            "space_id": record.space_id,
            "actor_id": record.actor_id,
            "visibility": record.visibility,
            "memory_type": record.memory_type,
        }

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
    if any(keyword in text for keyword in ("另一个群", "其他群", "别的群", "跨群", "不是这个群")):
        tags.append("跨群")
    if "私聊" in text:
        tags.append("私聊")
    if any(keyword in text for keyword in ("刚刚", "刚才", "最近", "上一句", "前面")):
        tags.append("最近消息")
    if any(keyword in text for keyword in ("吗", "什么", "怎么", "为何", "为什么", "？", "?")):
        tags.append("提问")
    if any(keyword in text for keyword in ("图片", "[图片]", "照片", "图")):
        tags.append("图片")
    if "@" in text or "[@" in text:
        tags.append("@")
    if is_behavior_instruction_text(text):
        tags.append("行为指令")
    if any(keyword in normalized for keyword in ("知识库", "聊天记录", "历史聊天", "数据库", "标签", "分门别类")):
        tags.append("知识库")
    if any(keyword in normalized for keyword in ("ai", "模型", "prompt", "提示词")):
        tags.append("AI")
    if any(keyword in normalized for keyword in ("代码", "项目", "提交")):
        tags.append("代码项目")
    if any(keyword in normalized for keyword in ("群管", "禁言", "复读", "管理")):
        tags.append("群管")
    return tuple(dict.fromkeys(tags))


def infer_rule_topics(text: str) -> tuple[str, ...]:
    normalized = text.lower()
    topics: list[str] = []
    if any(keyword in text for keyword in ("另一个群", "其他群", "别的群", "跨群", "不是这个群")):
        topics.append("跨群记忆")
    if any(keyword in text for keyword in ("刚刚", "刚才", "最近", "上一句", "前面", "聊天记录", "历史聊天")):
        topics.append("消息检索")
    if is_behavior_instruction_text(text):
        topics.append("行为指令")
    if any(keyword in normalized for keyword in ("知识库", "聊天记录", "历史聊天", "数据库", "标签", "分门别类")):
        topics.append("知识库")
    if any(keyword in normalized for keyword in ("shapez", "异形工厂")):
        topics.append("shapez")
    if any(keyword in normalized for keyword in ("ai", "模型", "prompt", "提示词", "长期记忆")):
        topics.append("AI")
    if any(keyword in normalized for keyword in ("代码", "项目", "提交")):
        topics.append("代码项目")
    if any(keyword in normalized for keyword in ("群管", "禁言", "复读", "管理")):
        topics.append("群管")
    return tuple(dict.fromkeys(topics))


def extract_rule_entities(text: str) -> tuple[str, ...]:
    entities: list[str] = []
    entities.extend(re.findall(r"\b\d{5,12}\b", text))
    entities.extend(re.findall(r"\b[A-Za-z][A-Za-z0-9_\-]{2,}\b", text))
    for marker in ("萌泪", "萌泪酱", "可可", "棉花糖", "shapez"):
        if marker.lower() in text.lower():
            entities.append(marker)
    return tuple(dict.fromkeys(entities))


def infer_importance(text: str) -> float:
    if is_prompt_injection_like(text):
        return 0.1
    if is_behavior_instruction_text(text):
        return 0.75
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


def is_sensitive_memory_claim_text(text: str) -> bool:
    return any(keyword in text for keyword in ("另一个群", "其他群", "别的群", "私聊内容", "私聊里"))


def is_behavior_instruction_text(text: str) -> bool:
    return any(
        keyword in text
        for keyword in (
            "说话结尾",
            "回复结尾",
            "结尾带",
            "句尾带",
            "遇到",
            "看到",
            "以后说话",
            "之后说话",
        )
    )


def is_group_visible_user_profile_fact(fact: ChatMemoryFact) -> bool:
    if fact.visibility != "private":
        return True
    return fact.predicate in GROUP_VISIBLE_PRIVATE_PROFILE_PREDICATES


def build_group_space_id(group_id: int | str) -> str:
    return f"qq:group:{str(group_id).strip()}"


def build_user_actor_id(user_id: int | str) -> str:
    normalized = str(user_id).strip()
    if normalized.startswith("qq:user:"):
        return normalized
    return f"qq:user:{normalized}"


def parse_qq_user_actor_id(actor_id: str) -> str:
    normalized = actor_id.strip()
    prefix = "qq:user:"
    return normalized[len(prefix) :] if normalized.startswith(prefix) else normalized


def extract_rule_facts(record: ChatMemoryRecord) -> tuple[ChatMemoryFact, ...]:
    if record.visibility == "private" and record.memory_type == "raw_message":
        return ()
    text = record.text.strip().strip("。！？!?.")
    if not text or is_prompt_injection_like(text):
        return ()

    facts: list[ChatMemoryFact] = []
    bot_target_user_id = extract_leading_at_user_id(text) if record.direction == "bot" else ""
    if bot_target_user_id:
        text = strip_leading_at_user(text)
    extracted = list(iter_behavior_instruction_parts(text))
    bot_target_nickname_parts = ()
    if bot_target_user_id:
        bot_target_nickname_parts = iter_bot_target_nickname_parts(bot_target_user_id, text)
        extracted.extend(bot_target_nickname_parts)
    if not bot_target_nickname_parts:
        extracted.extend(iter_rule_fact_parts(text))
    for subject, predicate, obj in extracted:
        if not subject or not obj or len(obj) > 80:
            continue
        topics = record.topics
        entities = tuple(dict.fromkeys([subject, *record.entities, *extract_rule_entities(obj)]))
        if predicate == "行为指令":
            topics = tuple(dict.fromkeys([*topics, "行为指令"]))
            entities = tuple(
                dict.fromkeys(
                    [
                        *entities,
                        "临时偏好",
                        "scope=group",
                        "permission=user",
                        "ttl=short",
                        *extract_behavior_instruction_entities(obj),
                    ]
                )
            )
        facts.append(
            ChatMemoryFact(
                id=0,
                group_id=record.group_id,
                subject=subject,
                predicate=predicate,
                object=obj,
                confidence=max(0.7, record.confidence),
                source_message_ids=(record.message_id,) if record.message_id else (),
                topics=topics,
                entities=entities,
                updated_at=record.timestamp,
                source_type="bot" if record.direction == "bot" else "user",
                trust_level="chat",
                status="active",
                space_id=record.space_id or build_group_space_id(record.group_id),
                visibility=record.visibility,
                memory_type="behavior_instruction" if predicate == "行为指令" else "fact",
            )
        )
    return tuple(facts)


def iter_behavior_instruction_parts(text: str) -> tuple[tuple[str, str, str], ...]:
    normalized = text.strip().strip("。！？!?.")
    if not normalized:
        return ()
    object_text = ""
    if re.search(r"(?:说话|回复)?结尾带(?P<object>[\w\u4e00-\u9fff]{1,12})", normalized):
        match = re.search(r"(?:说话|回复)?结尾带(?P<object>[\w\u4e00-\u9fff]{1,12})", normalized)
        if match is not None:
            object_text = f"说话结尾带{match.group('object')}"
    elif re.search(r"遇到(?P<object>.+)", normalized):
        object_text = normalized
    elif re.search(r"看到(?P<object>.+)", normalized):
        object_text = normalized
    if not object_text:
        return ()
    return (("群聊行为偏好", "行为指令", object_text.strip()),)


def extract_behavior_instruction_entities(text: str) -> tuple[str, ...]:
    entities: list[str] = []
    if "说话结尾" in text or "结尾带" in text:
        entities.append("说话结尾")
        entities.append("结尾")
    match = re.search(r"带(?P<object>[\w\u4e00-\u9fff]{1,12})", text)
    if match is not None:
        entities.append(match.group("object"))
    match = re.search(r"遇到(?P<object>[\w\u4e00-\u9fff]{1,20})", text)
    if match is not None:
        entities.append(match.group("object"))
    return tuple(dict.fromkeys(entity for entity in entities if entity))


def iter_rule_fact_parts(text: str) -> tuple[tuple[str, str, str], ...]:
    if is_question_like_fact_text(text):
        return ()
    patterns = [
        (
            r"^(?P<subject>[\w\u4e00-\u9fff]{1,20})不喜欢(?P<object>.+)$",
            "不喜欢",
        ),
        (
            r"^(?P<subject>[\w\u4e00-\u9fff]{1,20}?)(?:以后|之后|现在)?叫(?P<object>.+)$",
            "昵称",
        ),
        (
            r"^(?P<subject>[\w\u4e00-\u9fff]{1,20})是(?P<object>.+)的(?P<predicate>主人|管理员|作者)$",
            None,
        ),
        (
            r"^(?:以后)?规则是(?P<object>.+)$",
            "规则",
        ),
        (
            r"^(?P<subject>[\w\u4e00-\u9fff]{1,20})(?P<predicate>喜欢|是|在做|正在做|想要|需要)(?P<object>.+)$",
            None,
        ),
        (
            r"^(?P<subject>[\w\u4e00-\u9fff]{1,20})的(?P<predicate>身份|项目|需求|昵称)是(?P<object>.+)$",
            None,
        ),
    ]
    parts: list[tuple[str, str, str]] = []
    for pattern in patterns:
        expression, fixed_predicate = pattern
        match = re.match(expression, text)
        if match is None:
            continue
        subject = (match.groupdict().get("subject") or "群规则").strip()
        predicate = (fixed_predicate or match.groupdict().get("predicate") or "").strip()
        obj = (match.groupdict().get("object") or "").strip().strip("，,：:")
        if predicate == "是" and any(keyword in obj for keyword in ("群友", "管理员", "作者", "主人")):
            predicate = "身份"
        parts.append((subject, predicate, obj))
        break
    return tuple(parts)


def iter_bot_target_nickname_parts(
    target_user_id: str,
    text: str,
) -> tuple[tuple[str, str, str], ...]:
    match = re.search(
        r"(?:以后|之后|现在)?叫你(?P<object>[\w\u4e00-\u9fff-]{1,24}?)"
        r"(?:总行了吧|可以吗|行吗|吧|啦|了|。|！|，|,|$)",
        text,
    )
    if match is None:
        return ()
    nickname = match.group("object").strip("，,。！？!?.；;：:")
    if not nickname:
        return ()
    return ((target_user_id, "昵称", nickname),)


def extract_leading_at_user_id(text: str) -> str:
    match = re.match(r"^\[@(?P<user_id>\d{5,12})\]\s*", text.strip())
    return match.group("user_id") if match is not None else ""


def strip_leading_at_user(text: str) -> str:
    return re.sub(r"^\[@\d{5,12}\]\s*", "", text.strip(), count=1)


def is_question_like_fact_text(text: str) -> bool:
    normalized = text.strip()
    if any(mark in normalized for mark in ("?", "？")):
        return True
    compact = re.sub(r"\s+", "", normalized)
    return compact.endswith(("是谁", "是什么", "叫什么", "哪位", "哪个", "哪一个"))


def is_protected_chat_fact(fact: ChatMemoryFact) -> bool:
    if fact.trust_level != "chat" or fact.source_type not in {"user", "bot"}:
        return False
    normalized_subject = fact.subject.strip().lower()
    normalized_object = fact.object.strip().lower()
    if normalized_subject in {subject.lower() for subject in PROTECTED_FACT_SUBJECTS}:
        return True
        if fact.predicate in PROTECTED_FACT_PREDICATES and any(
            keyword.lower() == normalized_object for keyword in PROTECTED_FACT_OBJECT_KEYWORDS
        ):
            return True
    if fact.predicate in {"主人", "管理员", "作者"} and normalized_object in {
        item.lower() for item in PROTECTED_FACT_RELATION_OBJECTS
    }:
        return True
    return False


def strongest_source_type(left: str, right: str) -> str:
    order = {"user": 0, "bot": 1, "admin": 2, "system": 3}
    return left if order.get(left, 0) >= order.get(right, 0) else right


def strongest_trust_level(left: str, right: str) -> str:
    order = {"chat": 0, "bot": 1, "admin": 2, "system": 3}
    return left if order.get(left, 0) >= order.get(right, 0) else right


def fact_strength(fact: ChatMemoryFact) -> tuple[int, int, float, int]:
    trust_order = {"chat": 0, "bot": 1, "admin": 2, "system": 3}
    source_order = {"user": 0, "bot": 1, "admin": 2, "system": 3}
    return (
        trust_order.get(fact.trust_level, 0),
        source_order.get(fact.source_type, 0),
        fact.confidence,
        fact.updated_at,
    )


def is_stronger_fact(existing: ChatMemoryFact, incoming: ChatMemoryFact) -> bool:
    return fact_strength(existing) > fact_strength(incoming)


def is_mutually_exclusive_fact(fact: ChatMemoryFact) -> bool:
    return fact.predicate in MUTUALLY_EXCLUSIVE_FACT_PREDICATES or fact.memory_type == "behavior_instruction"


def is_behavior_instruction_active(
    fact: ChatMemoryFact,
    *,
    now: int | float | None = None,
) -> bool:
    if fact.memory_type != "behavior_instruction":
        return True
    if fact.trust_level in {"admin", "system"}:
        return True
    metadata = parse_behavior_instruction_entities(fact.entities)
    if metadata.get("ttl") != "short":
        return True
    current_time = int(now if now is not None else time.time())
    # 普通群友临时偏好只保留短时间，避免一句“以后都带喵”长期污染系统提示。
    return current_time - fact.updated_at <= BEHAVIOR_INSTRUCTION_SHORT_TTL_SECONDS


def parse_behavior_instruction_entities(entities: tuple[str, ...]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for entity in entities:
        if "=" not in entity:
            continue
        key, value = entity.split("=", 1)
        if key and value:
            metadata[key] = value
    return metadata


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
    score = (
        fact.confidence
        + TRUST_LEVEL_WEIGHT.get(fact.trust_level, 0.0)
        + SOURCE_TYPE_WEIGHT.get(fact.source_type, 0.0)
        + STATUS_WEIGHT.get(fact.status, -4.0)
    )
    for term in terms:
        if term == fact.subject or term in fact.entities:
            score += 3.0
        if term == fact.predicate:
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
    normalized_query = query.strip()
    normalized_parts = [part for part in normalized_query.split() if part]
    candidate_phrases = [normalized_query, *normalized_parts]
    for suffix in ("是谁", "是什么", "叫什么", "喜欢什么"):
        for phrase in candidate_phrases:
            if phrase.endswith(suffix) and len(phrase) > len(suffix):
                terms.append(phrase[: -len(suffix)])
    for suffix, predicate in (
        ("不喜欢什么", "不喜欢"),
        ("喜欢什么", "喜欢"),
        ("叫什么", "昵称"),
        ("研究什么", "研究"),
    ):
        for phrase in candidate_phrases:
            if suffix == "喜欢什么" and phrase.endswith("不喜欢什么"):
                continue
            if phrase.endswith(suffix):
                terms.append(predicate)
    for marker in ("喜欢", "不喜欢", "研究"):
        if marker in query:
            terms.append(marker)
    for marker in (
        "行为指令",
        "说话结尾",
        "结尾",
        "喵",
        "勺子鱼",
        "跨群",
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
        "代码项目",
        "AI",
        "群管",
        "禁言",
        "复读",
    ):
        if marker.lower() in query.lower():
            terms.append(marker)
    terms.extend(extract_rule_entities(query))
    return [term for term in dict.fromkeys(terms) if term]
