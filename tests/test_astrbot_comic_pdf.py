from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "plugins" / "astrbot_plugin_qqbot_features" / "comic_pdf"
PACKAGE_NAME = "qqbot_comic_pdf_test_package"
MAIN_PATH = ROOT / "plugins" / "astrbot_plugin_qqbot_features" / "main.py"


def _load_package():
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        PACKAGE_ROOT / "__init__.py",
        submodule_search_locations=[str(PACKAGE_ROOT)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)
    return module


comic_pdf = _load_package()
models = __import__(f"{PACKAGE_NAME}.models", fromlist=["DownloadedComic"])


class FakeOption:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.root = Path(config["dir_rule"]["base_dir"])

    def decide_image_save_dir(self, photo, ensure_exists: bool = False) -> str:
        return str(self.root / "1218951" / str(photo.album_index))


class FakeJmOption:
    last_config: dict | None = None

    @classmethod
    def construct(cls, config: dict) -> FakeOption:
        cls.last_config = config
        return FakeOption(config)


class FakeAlbum:
    title = "测试作品"

    def __init__(self, photos: list[object]) -> None:
        self.photos = photos

    def __iter__(self):
        return iter(self.photos)


class FakeJmModule:
    __version__ = "2.7.2"
    JmOption = FakeJmOption

    @staticmethod
    async def download_album_async(album_id: str, *, option: FakeOption):
        photos = [
            SimpleNamespace(album_index=1, title="第一章"),
            SimpleNamespace(album_index=2, title="第二章"),
        ]
        for photo in photos:
            chapter = Path(option.decide_image_save_dir(photo))
            chapter.mkdir(parents=True)
            (chapter / "10.jpg").write_bytes(b"ten")
            (chapter / "2.jpg").write_bytes(b"two")
        return SimpleNamespace(detail=FakeAlbum(photos))


class FakePdfBackend:
    @staticmethod
    def convert(paths: list[str], *, outputstream) -> None:
        outputstream.write(b"x" * (600 * len(paths)))


def test_adapter_normalizes_order_and_disables_system_proxy(tmp_path: Path) -> None:
    adapter = comic_pdf.JmcomicAdapter(module=FakeJmModule())

    result = asyncio.run(adapter.download_album("1218951", tmp_path / "download"))

    assert result.page_count == 4
    assert [path.name for path in result.chapters[0].pages] == ["2.jpg", "10.jpg"]
    assert FakeJmOption.last_config is not None
    proxies = FakeJmOption.last_config["client"]["postman"]["meta_data"]["proxies"]
    assert proxies == {}


def test_adapter_rejects_incompatible_version(tmp_path: Path) -> None:
    module = FakeJmModule()
    module.__version__ = "9.9.9"
    adapter = comic_pdf.JmcomicAdapter(module=module)

    with pytest.raises(comic_pdf.ComicDownloadError, match="版本不兼容"):
        asyncio.run(adapter.download_album("1218951", tmp_path / "download"))


def test_adapter_rejects_path_escape(tmp_path: Path) -> None:
    class EscapingOption(FakeOption):
        def decide_image_save_dir(self, photo, ensure_exists: bool = False) -> str:
            return str(self.root.parent / "outside")

    class EscapingJmOption(FakeJmOption):
        @classmethod
        def construct(cls, config: dict) -> EscapingOption:
            return EscapingOption(config)

    class EscapingModule(FakeJmModule):
        JmOption = EscapingJmOption

        @staticmethod
        async def download_album_async(album_id: str, *, option: FakeOption):
            outside = Path(option.decide_image_save_dir(SimpleNamespace(album_index=1)))
            outside.mkdir(parents=True)
            (outside / "1.jpg").write_bytes(b"page")
            return SimpleNamespace(
                detail=FakeAlbum([SimpleNamespace(album_index=1, title="escape")])
            )

    with pytest.raises(comic_pdf.ComicDownloadError, match="路径越界"):
        asyncio.run(
            comic_pdf.JmcomicAdapter(module=EscapingModule()).download_album(
                "1218951", tmp_path / "download"
            )
        )


def _downloaded_comic(tmp_path: Path):
    chapters = []
    for chapter_index in (1, 2):
        pages = []
        for page_index in (1, 2):
            path = tmp_path / f"c{chapter_index}-{page_index}.jpg"
            path.write_bytes(b"page")
            pages.append(path)
        chapters.append(
            comic_pdf.ComicChapter(
                index=chapter_index,
                title=f"章节{chapter_index}",
                pages=tuple(pages),
            )
        )
    return models.DownloadedComic("1218951", "测试/作品", tuple(chapters))


def test_config_clamps_resource_limits() -> None:
    config = comic_pdf.load_comic_pdf_config(
        {
            "jmcomic_timeout_seconds": 1,
            "jmcomic_max_pages_per_pdf": 5000,
            "jmcomic_max_pdf_size_mb": 1,
            "jmcomic_max_concurrent_jobs": 99,
        }
    )

    assert config.timeout_seconds == 60
    assert config.max_pages_per_pdf == 1000
    assert config.max_pdf_bytes == 10 * 1024 * 1024
    assert config.max_concurrent_jobs == 2
    assert config.owner_qq == "605738729"


def test_private_sender_uses_onebot_file_action(tmp_path: Path) -> None:
    pdf = tmp_path / "comic.pdf"
    pdf.write_bytes(b"pdf")
    calls: list[tuple[str, dict[str, object]]] = []

    class Api:
        async def call_api(self, action: str, **kwargs):
            calls.append((action, kwargs))

    artifact = comic_pdf.ComicPdfArtifact(pdf, 3, (1,))
    uploaded = asyncio.run(comic_pdf.upload_private_pdfs(Api(), 605738729, [artifact]))

    assert uploaded == 1
    assert calls == [
        (
            "upload_private_file",
            {"user_id": 605738729, "file": str(pdf.resolve()), "name": "comic.pdf"},
        )
    ]


def test_main_registers_owner_private_jmcomic_command() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")

    assert 'JMCOMIC_DOWNLOAD_PATTERN = r"(?i)^jm\\s*下载\\s*([0-9]+)$"' in source
    assert 'command_type="jmcomic_pdf"' in source
    assert 'if not event.is_private_chat():' in source
    assert 'str(event.get_sender_id() or "").strip() != self._comic_pdf_config.owner_qq' in source
    assert 'await asyncio.to_thread(job.cleanup)' in source
    assert source.index('await asyncio.to_thread(job.cleanup)') < source.index('yield event.plain_result(response_text)')


def test_renderer_keeps_bounded_whole_book(tmp_path: Path) -> None:
    renderer = comic_pdf.PdfRenderer(
        max_pages=500,
        max_bytes=10_000,
        module=FakePdfBackend(),
    )

    artifacts = renderer.render(_downloaded_comic(tmp_path), tmp_path / "pdf")

    assert len(artifacts) == 1
    assert artifacts[0].page_count == 4
    assert artifacts[0].path.name == "JM1218951-测试_作品.pdf"
    assert not artifacts[0].path.with_suffix(".pdf.part").exists()


def test_renderer_splits_oversized_book_and_chapters(tmp_path: Path) -> None:
    renderer = comic_pdf.PdfRenderer(
        max_pages=500,
        max_bytes=1024,
        module=FakePdfBackend(),
    )

    artifacts = renderer.render(_downloaded_comic(tmp_path), tmp_path / "pdf")

    assert len(artifacts) == 4
    assert all(artifact.page_count == 1 for artifact in artifacts)
    assert all(artifact.path.stat().st_size == 600 for artifact in artifacts)


def test_service_cleans_failed_and_completed_jobs(tmp_path: Path) -> None:
    class Adapter:
        async def download_album(self, album_id: str, task_root: Path):
            task_root.mkdir(parents=True)
            return _downloaded_comic(task_root)

    renderer = comic_pdf.PdfRenderer(
        max_pages=500,
        max_bytes=10_000,
        module=FakePdfBackend(),
    )
    service = comic_pdf.ComicPdfService(
        tmp_path / "jobs",
        comic_pdf.ComicPdfConfig(timeout_seconds=5),
        adapter_factory=lambda: Adapter(),
        renderer_factory=lambda: renderer,
    )

    job = asyncio.run(service.create_pdf("1218951"))
    assert job.artifacts[0].path.exists()
    job.cleanup()
    assert not job.task_root.exists()

    class FailingAdapter:
        async def download_album(self, album_id: str, task_root: Path):
            task_root.mkdir(parents=True)
            raise comic_pdf.ComicDownloadError("failed")

    failing = comic_pdf.ComicPdfService(
        tmp_path / "failed-jobs",
        adapter_factory=lambda: FailingAdapter(),
    )
    with pytest.raises(comic_pdf.ComicDownloadError):
        asyncio.run(failing.create_pdf("1218951"))
    assert not list((tmp_path / "failed-jobs").glob("*"))


def test_service_serializes_jobs(tmp_path: Path) -> None:
    active = 0
    peak = 0

    class SlowAdapter:
        async def download_album(self, album_id: str, task_root: Path):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            task_root.mkdir(parents=True)
            active -= 1
            return _downloaded_comic(task_root)

    service = comic_pdf.ComicPdfService(
        tmp_path / "jobs",
        comic_pdf.ComicPdfConfig(max_concurrent_jobs=1),
        adapter_factory=lambda: SlowAdapter(),
        renderer_factory=lambda: comic_pdf.PdfRenderer(
            max_pages=500,
            max_bytes=10_000,
            module=FakePdfBackend(),
        ),
    )

    async def run_jobs():
        return await asyncio.gather(
            service.create_pdf("1218951"),
            service.create_pdf("1218952"),
        )

    jobs = asyncio.run(run_jobs())
    assert peak == 1
    for job in jobs:
        job.cleanup()
