from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil


class ComicPdfError(RuntimeError):
    """Base error safe to report without upstream response details."""


class ComicDownloadError(ComicPdfError):
    """Raised when the pinned JMComic adapter cannot complete a download."""


@dataclass(frozen=True, slots=True)
class ComicPdfConfig:
    """Resource and compatibility limits for one comic PDF service."""

    enabled: bool = True
    owner_qq: str = "605738729"
    proxy: str = ""
    timeout_seconds: int = 1800
    max_pages_per_pdf: int = 500
    max_pdf_bytes: int = 100 * 1024 * 1024
    max_concurrent_jobs: int = 1


@dataclass(frozen=True, slots=True)
class ComicChapter:
    """One ordered chapter and its downloaded page files."""

    index: int
    title: str
    pages: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class DownloadedComic:
    """Bot-owned normalized result returned by an upstream adapter."""

    album_id: str
    title: str
    chapters: tuple[ComicChapter, ...]

    @property
    def page_count(self) -> int:
        """Return the total number of downloaded pages."""
        return sum(len(chapter.pages) for chapter in self.chapters)


@dataclass(frozen=True, slots=True)
class ComicPdfArtifact:
    """One generated PDF ready for transport."""

    path: Path
    page_count: int
    chapter_indexes: tuple[int, ...]


@dataclass(slots=True)
class ComicPdfJob:
    """Generated artifacts whose task directory must be cleaned after upload."""

    album_id: str
    title: str
    task_root: Path
    artifacts: tuple[ComicPdfArtifact, ...]

    def cleanup(self) -> None:
        """Remove all downloaded and generated files for this job."""
        shutil.rmtree(self.task_root, ignore_errors=True)
