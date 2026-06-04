from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import time


TRUSTED_STATUS = "trusted"
CANDIDATE_STATUS = "candidate"
CONFLICT_STATUS = "conflict"
STALE_STATUS = "stale_pending_review"


@dataclass(frozen=True, slots=True)
class DomainKnowledgeRecord:
    id: str
    status: str
    domain: str
    space_id: str
    source_type: str
    source_uri: str
    title: str
    summary: str
    evidence: str
    source_hash: str
    trust_level: str
    risk: str
    updated_at: int
    stale_of: str = ""


class DomainKnowledgeStore:
    def __init__(self, data_root: Path) -> None:
        self.path = Path(data_root) / "ai" / "domain_knowledge.json"

    def upsert_candidate(
        self,
        *,
        domain: str,
        space_id: str,
        source_type: str,
        source_uri: str,
        title: str,
        summary: str,
        evidence: str = "",
        trust_level: str = "candidate",
        risk: str = "low",
        auto_trust: bool = False,
        now: int | None = None,
    ) -> DomainKnowledgeRecord:
        now = now if now is not None else int(time.time())
        source_hash = _hash_text(f"{source_uri}\n{summary}\n{evidence}")
        record_id = _knowledge_id(domain, space_id, source_uri)
        records = list(self.list_records(limit=10_000))
        existing = next((record for record in records if record.id == record_id), None)
        status = TRUSTED_STATUS if auto_trust and risk == "low" else CANDIDATE_STATUS
        stale_of = ""
        if existing is not None and existing.source_hash != source_hash:
            if existing.status == TRUSTED_STATUS and not auto_trust:
                status = STALE_STATUS
                stale_of = existing.id
            elif existing.summary and existing.summary != summary:
                status = CONFLICT_STATUS
                stale_of = existing.id
        record = DomainKnowledgeRecord(
            id=record_id,
            status=status,
            domain=domain,
            space_id=space_id,
            source_type=source_type,
            source_uri=source_uri,
            title=title.strip() or source_uri,
            summary=summary.strip(),
            evidence=evidence.strip(),
            source_hash=source_hash,
            trust_level=trust_level,
            risk=risk,
            updated_at=now,
            stale_of=stale_of,
        )
        next_records = [item for item in records if item.id != record.id]
        next_records.append(record)
        self._write_records(next_records)
        return record

    def list_records(
        self,
        *,
        status: str = "",
        domain: str = "",
        limit: int = 100,
    ) -> tuple[DomainKnowledgeRecord, ...]:
        if not self.path.exists():
            return ()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ()
        records: list[DomainKnowledgeRecord] = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            record = DomainKnowledgeRecord(
                id=str(item.get("id", "")),
                status=str(item.get("status", "")),
                domain=str(item.get("domain", "")),
                space_id=str(item.get("space_id", "")),
                source_type=str(item.get("source_type", "")),
                source_uri=str(item.get("source_uri", "")),
                title=str(item.get("title", "")),
                summary=str(item.get("summary", "")),
                evidence=str(item.get("evidence", "")),
                source_hash=str(item.get("source_hash", "")),
                trust_level=str(item.get("trust_level", "")),
                risk=str(item.get("risk", "")),
                updated_at=int(item.get("updated_at", 0) or 0),
                stale_of=str(item.get("stale_of", "")),
            )
            if status and record.status != status:
                continue
            if domain and record.domain != domain:
                continue
            records.append(record)
        records.sort(key=lambda item: (-item.updated_at, item.domain, item.title))
        return tuple(records[: max(1, limit)])

    def set_status(self, record_id: str, status: str) -> bool:
        if status not in {TRUSTED_STATUS, CANDIDATE_STATUS, CONFLICT_STATUS, STALE_STATUS, "disabled"}:
            raise ValueError(f"Unsupported knowledge status: {status}")
        records = list(self.list_records(limit=10_000))
        updated = False
        now = int(time.time())
        next_records: list[DomainKnowledgeRecord] = []
        for record in records:
            if record.id != record_id:
                next_records.append(record)
                continue
            next_records.append(
                DomainKnowledgeRecord(
                    id=record.id,
                    status=status,
                    domain=record.domain,
                    space_id=record.space_id,
                    source_type=record.source_type,
                    source_uri=record.source_uri,
                    title=record.title,
                    summary=record.summary,
                    evidence=record.evidence,
                    source_hash=record.source_hash,
                    trust_level=record.trust_level,
                    risk=record.risk,
                    updated_at=now,
                    stale_of=record.stale_of,
                )
            )
            updated = True
        if updated:
            self._write_records(next_records)
        return updated

    def _write_records(self, records: list[DomainKnowledgeRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(record) for record in records]
        tmp_path = self.path.with_name(f"{self.path.name}.{time.time_ns()}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)


def build_seed_knowledge_candidates() -> tuple[dict[str, str], ...]:
    return (
        {
            "domain": "shapez",
            "space_id": "qq:group:1163635014",
            "source_type": "local_docs_rule",
            "source_uri": "D:/Desktop/游戏/异形工厂",
            "title": "shapez 本地资料目录",
            "summary": "该目录下资料允许用于 shapez 群基础知识总结；第一阶段不自动索引完整聊天记录。",
            "evidence": "用户在 2026-05-30 确认 D:/Desktop/游戏/异形工厂 下资料都可以看并总结。",
            "trust_level": "admin",
            "risk": "low",
            "auto_trust": "true",
        },
        {
            "domain": "shapez",
            "space_id": "qq:group:1163635014",
            "source_type": "group_file_rule",
            "source_uri": "group-file:1163635014:萌新必看|速通",
            "title": "shapez 群文件筛选规则",
            "summary": "只优先阅读“萌新必看”“速通”类群文件；高阶电路类资料第一阶段不纳入。",
            "evidence": "用户在 2026-05-30 指定群文件筛选范围。",
            "trust_level": "admin",
            "risk": "low",
            "auto_trust": "true",
        },
        {
            "domain": "fractionate_everything",
            "space_id": "qq:group:319567534",
            "source_type": "workflow_rule",
            "source_uri": "memory:mlj_dspmods:fe-bug-boundary",
            "title": "FE bug 处理边界",
            "summary": "FE bug 只做解释、证据整理和需求记录；不要承诺或触发自动修改代码。",
            "evidence": "用户在 2026-06-04 确认不需要 AI 修复 bug 类功能。",
            "trust_level": "admin",
            "risk": "medium",
            "auto_trust": "true",
        },
    )


def _knowledge_id(domain: str, space_id: str, source_uri: str) -> str:
    return _hash_text(f"{domain}\n{space_id}\n{source_uri}")[:20]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
