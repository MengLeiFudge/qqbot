from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time

from qqbot.services.message_delivery import call_split_text_api


@dataclass(frozen=True, slots=True)
class CodexSelfUpdateNotice:
    target_type: str
    target_id: str
    project_display_name: str
    source_label: str
    created_at: int


class CodexSelfUpdateNoticeStore:
    def __init__(self, data_root: Path) -> None:
        self.path = Path(data_root) / "ai" / "codex_self_update_notices.json"

    def add_notice(
        self,
        *,
        target_type: str,
        target_id: str,
        project_display_name: str,
        source_label: str,
    ) -> None:
        if target_type not in {"group", "private"}:
            return
        if not target_id.strip().isdigit():
            return
        notices = list(self.list_notices())
        notices.append(
            CodexSelfUpdateNotice(
                target_type=target_type,
                target_id=target_id.strip(),
                project_display_name=project_display_name,
                source_label=source_label,
                created_at=int(time.time()),
            )
        )
        self._write_notices(tuple(notices))

    def list_notices(self) -> tuple[CodexSelfUpdateNotice, ...]:
        if not self.path.exists():
            return ()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return ()
        return tuple(
            CodexSelfUpdateNotice(
                target_type=str(item.get("target_type", "")),
                target_id=str(item.get("target_id", "")),
                project_display_name=str(item.get("project_display_name", "")),
                source_label=str(item.get("source_label", "")),
                created_at=int(item.get("created_at", 0)),
            )
            for item in payload
            if isinstance(item, dict)
        )

    def pop_all(self) -> tuple[CodexSelfUpdateNotice, ...]:
        notices = self.list_notices()
        self._write_notices(())
        return notices

    def _write_notices(self, notices: tuple[CodexSelfUpdateNotice, ...]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(notice) for notice in notices], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


async def publish_pending_codex_self_update_notices(bot, data_root: Path) -> int:
    notices = CodexSelfUpdateNoticeStore(data_root).pop_all()
    sent = 0
    for notice in notices:
        message = (
            f"Codex 自我更新已重启完成：{notice.project_display_name}\n"
            f"来源：{notice.source_label}\n"
            "当前 OneBot 已重新连接。"
        )
        if notice.target_type == "group":
            await call_split_text_api(
                bot,
                "send_group_msg",
                group_id=int(notice.target_id),
                message=message,
            )
            sent += 1
        elif notice.target_type == "private":
            await call_split_text_api(
                bot,
                "send_private_msg",
                user_id=int(notice.target_id),
                message=message,
            )
            sent += 1
    return sent
