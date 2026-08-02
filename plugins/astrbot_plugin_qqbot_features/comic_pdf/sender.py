from __future__ import annotations

from collections.abc import Iterable

from .models import ComicPdfArtifact, ComicPdfError


async def upload_private_pdfs(api, user_id: int, artifacts: Iterable[ComicPdfArtifact]) -> int:
    """Upload generated PDFs through the NapCat private-file extension."""
    return await _upload(api, "upload_private_file", "user_id", user_id, artifacts)


async def upload_group_pdfs(api, group_id: int, artifacts: Iterable[ComicPdfArtifact]) -> int:
    """Upload generated PDFs to a QQ group for an authorized integration test."""
    return await _upload(api, "upload_group_file", "group_id", group_id, artifacts)


async def _upload(api, action: str, target_key: str, target_id: int, artifacts: Iterable[ComicPdfArtifact]) -> int:
    uploaded = 0
    for artifact in artifacts:
        path = artifact.path.resolve()
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise ComicPdfError("待发送 PDF 不存在，任务已终止。")
        await api.call_api(
            action,
            **{
                target_key: int(target_id),
                "file": str(path),
                "name": path.name,
            },
        )
        uploaded += 1
    return uploaded
