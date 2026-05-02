from pathlib import Path
import asyncio
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.codex_self_update_service import (
    CodexSelfUpdateNoticeStore,
    publish_pending_codex_self_update_notices,
)


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_api(self, api: str, **data: object) -> None:
        self.calls.append((api, data))


def test_publish_pending_codex_self_update_group_notice(tmp_path: Path) -> None:
    store = CodexSelfUpdateNoticeStore(tmp_path)
    store.add_notice(
        target_type="group",
        target_id="1163635014",
        project_display_name="qqbot",
        source_label="Codex 会话 CODEX-S0001",
    )
    bot = FakeBot()

    sent = asyncio.run(publish_pending_codex_self_update_notices(bot, tmp_path))

    assert sent == 1
    assert bot.calls == [
        (
            "send_group_msg",
            {
                "group_id": 1163635014,
                "message": (
                    "Codex 自我更新已重启完成：qqbot\n"
                    "来源：Codex 会话 CODEX-S0001\n"
                    "当前 OneBot 已重新连接。"
                ),
            },
        )
    ]
    assert store.list_notices() == ()
