from __future__ import annotations

from collections.abc import Iterable

from .models import ComicPdfArtifact, ComicPdfError


async def send_private_pdfs_with_password(
    api,
    user_id: int,
    album_id: str,
    artifacts: Iterable[ComicPdfArtifact],
) -> int:
    """Send each private file, then reply to that file with its JMID password."""
    password = str(album_id or "").strip()
    if not password.isdigit():
        raise ComicPdfError("JM PDF 密码无法由作品 ID 生成。")
    sent = 0
    for artifact in artifacts:
        path = artifact.path.resolve()
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise ComicPdfError("待发送 PDF 不存在，任务已终止。")
        result = await api.call_api(
            "send_private_msg",
            user_id=int(user_id),
            message=[
                {
                    "type": "file",
                    "data": {"file": str(path), "name": path.name},
                }
            ],
        )
        message_id = _message_id(result)
        if not message_id:
            raise ComicPdfError("PDF 已上传，但无法取得文件消息 ID。")
        await api.call_api(
            "send_private_msg",
            user_id=int(user_id),
            message=[
                {"type": "reply", "data": {"id": message_id}},
                {"type": "text", "data": {"text": f"下载完成，密码{password}"}},
            ],
        )
        sent += 1
    return sent


def _message_id(result: object) -> str:
    if isinstance(result, dict):
        value = result.get("message_id")
        if value is None and isinstance(result.get("data"), dict):
            value = result["data"].get("message_id")
        return str(value or "").strip()
    return ""
