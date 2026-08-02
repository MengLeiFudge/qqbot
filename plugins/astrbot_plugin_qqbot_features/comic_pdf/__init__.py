"""Stable bot-owned contracts for JMComic downloads and PDF rendering."""

from .adapter import JmcomicAdapter
from .config import load_comic_pdf_config
from .models import (
    ComicChapter,
    ComicDownloadError,
    ComicPdfArtifact,
    ComicPdfConfig,
    ComicPdfError,
    ComicPdfJob,
)
from .renderer import PdfRenderer
from .sender import upload_group_pdfs, upload_private_pdfs
from .service import ComicPdfService

__all__ = [
    "ComicChapter",
    "ComicDownloadError",
    "ComicPdfArtifact",
    "ComicPdfConfig",
    "ComicPdfError",
    "ComicPdfJob",
    "ComicPdfService",
    "JmcomicAdapter",
    "PdfRenderer",
    "load_comic_pdf_config",
    "upload_group_pdfs",
    "upload_private_pdfs",
]
