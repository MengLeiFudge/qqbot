from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_requirement_store import AiRequirementStore


def test_requirement_store_creates_and_lists_proposals(tmp_path: Path) -> None:
    store = AiRequirementStore(tmp_path)

    proposal = store.create_proposal(
        plugin_id="shapez",
        summary="支持 chart 短代码",
        evidence=("群友说需要重新艾特并粘贴短代码",),
        created_by="605738729",
        group_id="1163635014",
    )

    assert proposal.id == "REQ-0001"
    assert proposal.status == "pending"
    assert proposal.plugin_id == "shapez"
    assert store.list_proposals() == (proposal,)


def test_requirement_store_appends_ids(tmp_path: Path) -> None:
    store = AiRequirementStore(tmp_path)

    first = store.create_proposal("shapez", "需求1", ("证据1",), "10001")
    second = store.create_proposal("arc", "需求2", ("证据2",), "10001")

    assert first.id == "REQ-0001"
    assert second.id == "REQ-0002"
