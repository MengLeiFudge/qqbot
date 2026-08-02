from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
import shutil
import uuid

from .adapter import JmcomicAdapter
from .models import ComicDownloadError, ComicPdfConfig, ComicPdfError, ComicPdfJob
from .renderer import PdfRenderer


class ComicPdfService:
    """Coordinate one bounded JM download and PDF generation lifecycle."""

    def __init__(
        self,
        temp_root: Path,
        config: ComicPdfConfig | None = None,
        *,
        adapter_factory: Callable[[], JmcomicAdapter] | None = None,
        renderer_factory: Callable[[], PdfRenderer] | None = None,
    ) -> None:
        self.temp_root = Path(temp_root).resolve()
        self.config = config or ComicPdfConfig()
        self._adapter_factory = adapter_factory or (
            lambda: JmcomicAdapter(proxy=self.config.proxy)
        )
        self._renderer_factory = renderer_factory or (
            lambda: PdfRenderer(
                max_pages=self.config.max_pages_per_pdf,
                max_bytes=self.config.max_pdf_bytes,
            )
        )
        self._semaphore = asyncio.Semaphore(max(1, self.config.max_concurrent_jobs))

    async def create_pdf(self, album_id: str) -> ComicPdfJob:
        """Create a cleanup-owned PDF job under the configured temp root."""
        normalized_id = str(album_id or "").strip()
        if not normalized_id.isdigit():
            raise ComicDownloadError("JM 作品 ID 必须是纯数字。")
        async with self._semaphore:
            task_root = self.temp_root / f"jm{normalized_id}-{uuid.uuid4().hex}"
            try:
                task_root.mkdir(parents=True, exist_ok=False)
                comic = await asyncio.wait_for(
                    self._adapter_factory().download_album(
                        normalized_id,
                        task_root / "download",
                    ),
                    timeout=max(1, self.config.timeout_seconds),
                )
                artifacts = await asyncio.to_thread(
                    self._renderer_factory().render,
                    comic,
                    task_root / "pdf",
                )
                if not artifacts:
                    raise ComicPdfError("没有生成可发送的 PDF。")
                return ComicPdfJob(
                    album_id=normalized_id,
                    title=comic.title,
                    task_root=task_root,
                    artifacts=artifacts,
                )
            except TimeoutError as exc:
                shutil.rmtree(task_root, ignore_errors=True)
                raise ComicDownloadError("JM 下载超时，任务已清理。") from exc
            except BaseException:
                shutil.rmtree(task_root, ignore_errors=True)
                raise
