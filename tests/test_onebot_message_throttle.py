from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.onebot_message_throttle import extract_group_message_group_id


def test_extract_group_message_group_id_only_matches_group_messages() -> None:
    assert extract_group_message_group_id("send_group_msg", {"group_id": 10001}) == 10001
    assert (
        extract_group_message_group_id(
            "send_msg",
            {"message_type": "group", "group_id": "10002"},
        )
        == "10002"
    )
    assert extract_group_message_group_id("send_private_msg", {"user_id": 10001}) is None
    assert extract_group_message_group_id("group_poke", {"group_id": 10001}) is None
