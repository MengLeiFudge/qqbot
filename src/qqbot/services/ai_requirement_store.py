from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import time
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AiRequirementProposal:
    id: str
    plugin_id: str
    summary: str
    evidence: tuple[str, ...]
    created_by: str
    group_id: str | None
    status: str
    created_at: int


class AiRequirementStore:
    def __init__(self, data_root: Path) -> None:
        self.file_path = Path(data_root) / "ai" / "requirements.json"

    def create_proposal(
        self,
        plugin_id: str,
        summary: str,
        evidence: tuple[str, ...],
        created_by: str,
        group_id: str | None = None,
    ) -> AiRequirementProposal:
        proposals = list(self.list_proposals())
        proposal = AiRequirementProposal(
            id=f"REQ-{len(proposals) + 1:04d}",
            plugin_id=plugin_id.strip() or "unknown",
            summary=summary.strip(),
            evidence=tuple(item.strip() for item in evidence if item.strip()),
            created_by=str(created_by),
            group_id=str(group_id) if group_id else None,
            status="pending",
            created_at=int(time.time()),
        )
        proposals.append(proposal)
        self._write(proposals)
        return proposal

    def list_proposals(self) -> tuple[AiRequirementProposal, ...]:
        if not self.file_path.exists():
            return ()
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return ()
        proposals: list[AiRequirementProposal] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            proposals.append(
                AiRequirementProposal(
                    id=str(item.get("id", "")),
                    plugin_id=str(item.get("plugin_id", "")),
                    summary=str(item.get("summary", "")),
                    evidence=tuple(str(value) for value in item.get("evidence", [])),
                    created_by=str(item.get("created_by", "")),
                    group_id=(
                        str(item.get("group_id"))
                        if item.get("group_id") is not None
                        else None
                    ),
                    status=str(item.get("status", "pending")),
                    created_at=int(item.get("created_at", 0)),
                )
            )
        return tuple(proposals)

    def _write(self, proposals: list[AiRequirementProposal]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(
                [
                    {
                        **asdict(proposal),
                        "evidence": list(proposal.evidence),
                    }
                    for proposal in proposals
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
