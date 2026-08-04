from __future__ import annotations

import asyncio
import importlib.util
import json
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
    title = "完整测试标题"
    oname = "测试作品"
    author = "测试作者"
    tags = ["纯爱", "校园", "纯爱"]

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


def _downloaded_comic(tmp_path: Path, album_id: str = "1218951"):
    chapters = []
    for chapter_index in (1, 2):
        pages = []
        for page_index in (1, 2):
            path = tmp_path / f"c{chapter_index}-{page_index}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"page")
            pages.append(path)
        chapters.append(
            comic_pdf.ComicChapter(
                index=chapter_index,
                title=f"章节{chapter_index}",
                pages=tuple(pages),
            )
        )
    return models.DownloadedComic(
        album_id=album_id,
        author="测试/作者",
        title="测试:作品",
        chapters=tuple(chapters),
        tags=("测试标签", "长篇"),
    )


def _renderer(*, max_bytes: int = 10_000):
    return comic_pdf.PdfRenderer(
        max_pages=500,
        max_bytes=max_bytes,
        module=FakePdfBackend(),
    )


def test_adapter_normalizes_author_title_order_and_disables_system_proxy(tmp_path: Path) -> None:
    result = asyncio.run(
        comic_pdf.JmcomicAdapter(module=FakeJmModule()).download_album(
            "1218951", tmp_path / "download"
        )
    )

    assert result.author == "测试作者"
    assert result.title == "测试作品"
    assert result.tags == ("纯爱", "校园")
    assert result.page_count == 4
    assert [path.name for path in result.chapters[0].pages] == ["2.jpg", "10.jpg"]
    assert FakeJmOption.last_config is not None
    proxies = FakeJmOption.last_config["client"]["postman"]["meta_data"]["proxies"]
    assert proxies == {}


def test_adapter_rejects_incompatible_version(tmp_path: Path) -> None:
    module = FakeJmModule()
    module.__version__ = "9.9.9"
    with pytest.raises(comic_pdf.ComicDownloadError, match="版本不兼容"):
        asyncio.run(
            comic_pdf.JmcomicAdapter(module=module).download_album(
                "1218951", tmp_path / "download"
            )
        )


def test_config_clamps_resource_and_cache_limits() -> None:
    config = comic_pdf.load_comic_pdf_config(
        {
            "jmcomic_timeout_seconds": 1,
            "jmcomic_max_pages_per_pdf": 5000,
            "jmcomic_max_pdf_size_mb": 1,
            "jmcomic_max_concurrent_jobs": 99,
            "jmcomic_max_queued_jobs": 999,
            "jmcomic_cache_max_gb": 0,
        }
    )

    assert config.timeout_seconds == 60
    assert config.max_pages_per_pdf == 1000
    assert config.max_pdf_bytes == 10 * 1024 * 1024
    assert config.max_concurrent_jobs == 2
    assert config.max_queued_jobs == 100
    assert comic_pdf.load_comic_pdf_config({}).max_queued_jobs == 50
    assert config.cache_max_bytes == 1024**3


def test_private_sender_announces_metadata_then_sends_all_parts_and_completion(tmp_path: Path) -> None:
    first = tmp_path / "comic(1).pdf"
    second = tmp_path / "comic(2).pdf"
    first.write_bytes(b"pdf-1")
    second.write_bytes(b"pdf-2")
    calls: list[tuple[str, dict[str, object]]] = []

    class Api:
        async def call_api(self, action: str, **kwargs):
            calls.append((action, kwargs))
            return {}

    artifacts = [
        comic_pdf.ComicPdfArtifact(first, 3, (1,)),
        comic_pdf.ComicPdfArtifact(second, 2, (2,)),
    ]
    sent = asyncio.run(
        comic_pdf.send_private_pdfs_with_password(
            Api(),
            123456,
            "1218951",
            artifacts,
            title="测试作品",
            author="测试作者",
            tags=("纯爱", "校园"),
        )
    )

    assert sent == 2
    assert calls[0] == (
        "send_private_msg",
        {
            "user_id": 123456,
            "message": [
                {
                    "type": "text",
                    "data": {
                        "text": (
                            "JM1218951 加密完成，准备发送。\n"
                            "名称：JM1218951\n"
                            "标题：测试作品\n"
                            "作者：测试作者\n"
                            "标签：纯爱、校园\n"
                            "文件切片：共 2 份\n"
                            "密码：1218951"
                        )
                    },
                }
            ],
        },
    )
    assert [call[1]["message"][0]["data"]["name"] for call in calls[1:3]] == [
        "comic(1).pdf",
        "comic(2).pdf",
    ]
    assert calls[3] == (
        "send_private_msg",
        {
            "user_id": 123456,
            "message": [
                {"type": "text", "data": {"text": "JM1218951发送完成"}}
            ],
        },
    )
    assert all(
        segment["type"] != "reply"
        for _, kwargs in calls
        for segment in kwargs["message"]
    )


def test_private_sender_does_not_confirm_after_a_part_fails(tmp_path: Path) -> None:
    first = tmp_path / "comic(1).pdf"
    second = tmp_path / "comic(2).pdf"
    first.write_bytes(b"pdf-1")
    second.write_bytes(b"pdf-2")
    sent_texts: list[str] = []
    file_calls = 0

    class Api:
        async def call_api(self, action: str, **kwargs):
            nonlocal file_calls
            message = kwargs["message"]
            if message[0]["type"] == "text":
                sent_texts.append(message[0]["data"]["text"])
            else:
                file_calls += 1
                if file_calls == 2:
                    raise RuntimeError("upload failed")
            return {}

    artifacts = [
        comic_pdf.ComicPdfArtifact(first, 3, (1,)),
        comic_pdf.ComicPdfArtifact(second, 2, (2,)),
    ]
    with pytest.raises(RuntimeError, match="upload failed"):
        asyncio.run(
            comic_pdf.send_private_pdfs_with_password(
                Api(),
                123456,
                "1218951",
                artifacts,
                title="测试作品",
                author="测试作者",
            )
        )

    assert len(sent_texts) == 1
    assert "加密完成" in sent_texts[0]
    assert all("发送完成" not in text for text in sent_texts)


def test_renderer_keeps_bounded_whole_book(tmp_path: Path) -> None:
    artifacts = _renderer().render(_downloaded_comic(tmp_path), tmp_path / "pdf")

    assert len(artifacts) == 1
    assert artifacts[0].page_count == 4
    assert artifacts[0].path.name == "JM1218951-测试_作品.pdf"


def test_renderer_splits_oversized_book_and_chapters(tmp_path: Path) -> None:
    artifacts = _renderer(max_bytes=1024).render(
        _downloaded_comic(tmp_path), tmp_path / "pdf"
    )

    assert len(artifacts) == 4
    assert all(artifact.page_count == 1 for artifact in artifacts)
    assert all(artifact.path.stat().st_size == 600 for artifact in artifacts)


def test_cache_uses_required_folder_manifest_names_and_hashes(tmp_path: Path) -> None:
    cache = comic_pdf.ComicPdfCache(tmp_path / "cache", max_bytes=10_000)
    entry = cache.store(_downloaded_comic(tmp_path / "images"), _renderer(max_bytes=1024))

    assert entry.cache_dir.name == "JM1218951-【测试_作者】测试_作品"
    assert [item.path.name for item in entry.artifacts] == [
        f"{entry.cache_dir.name}({index}).pdf" for index in range(1, 5)
    ]
    manifest = json.loads((entry.cache_dir / "metadata.json").read_text(encoding="utf-8"))
    assert manifest["download_complete"] is True
    assert manifest["author"] == "测试/作者"
    assert manifest["title"] == "测试:作品"
    assert manifest["tags"] == ["测试标签", "长篇"]
    assert manifest["page_count"] == 4
    assert manifest["total_size_bytes"] == 2400
    assert all(len(item["sha256"]) == 64 for item in manifest["artifacts"])
    assert cache.lookup("1218951") is not None


def test_cache_accepts_legacy_manifest_without_tags(tmp_path: Path) -> None:
    cache = comic_pdf.ComicPdfCache(tmp_path / "cache", max_bytes=10_000)
    stored = cache.store(_downloaded_comic(tmp_path / "images"), _renderer())
    manifest_path = stored.cache_dir / "metadata.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("tags")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    entry = cache.lookup("1218951")

    assert entry is not None
    assert entry.tags == ()
    assert stored.cache_dir.is_dir()


def test_cache_discards_hash_mismatch_and_lru_evicts_oldest(tmp_path: Path) -> None:
    cache = comic_pdf.ComicPdfCache(tmp_path / "cache", max_bytes=3000)
    first = cache.store(_downloaded_comic(tmp_path / "one", "1001"), _renderer())
    second = cache.store(_downloaded_comic(tmp_path / "two", "1002"), _renderer())

    assert not first.cache_dir.exists()
    assert second.cache_dir.exists()
    second.artifacts[0].path.write_bytes(b"corrupt")
    assert cache.lookup("1002") is None
    assert not second.cache_dir.exists()


def test_service_singleflights_same_album(tmp_path: Path) -> None:
    async def scenario() -> None:
        calls = 0
        gate = asyncio.Event()

        class Adapter:
            async def download_album(self, album_id: str, task_root: Path):
                nonlocal calls
                calls += 1
                await gate.wait()
                return _downloaded_comic(task_root, album_id)

        service = comic_pdf.ComicPdfService(
            tmp_path / "jobs",
            comic_pdf.ComicPdfConfig(max_concurrent_jobs=2),
            cache_root=tmp_path / "cache",
            adapter_factory=lambda: Adapter(),
            renderer_factory=_renderer,
        )
        first = await service.submit("1218951")
        second = await service.submit("1218951")
        assert first.status == "started"
        assert second.status == "shared"
        gate.set()
        one, two = await asyncio.gather(first.wait(), second.wait())
        assert calls == 1
        assert one.cache_dir == two.cache_dir

    asyncio.run(scenario())


def test_service_runs_two_albums_and_reports_fifo_queue(tmp_path: Path) -> None:
    async def scenario() -> None:
        active = 0
        peak = 0
        gate = asyncio.Event()

        class Adapter:
            async def download_album(self, album_id: str, task_root: Path):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await gate.wait()
                active -= 1
                return _downloaded_comic(task_root, album_id)

        service = comic_pdf.ComicPdfService(
            tmp_path / "jobs",
            comic_pdf.ComicPdfConfig(max_concurrent_jobs=2, max_queued_jobs=2),
            cache_root=tmp_path / "cache",
            adapter_factory=lambda: Adapter(),
            renderer_factory=_renderer,
        )
        first = await service.submit("1001")
        second = await service.submit("1002")
        third = await service.submit("1003")
        shared_third = await service.submit("1003")
        assert (first.status, second.status) == ("started", "started")
        assert third.status == "queued"
        assert third.queue_position == 1
        assert shared_third.status == "shared"
        assert shared_third.queue_position == 1
        await asyncio.sleep(0)
        assert peak == 2
        gate.set()
        await asyncio.gather(first.wait(), second.wait(), third.wait())
        assert peak == 2

    asyncio.run(scenario())


def test_service_cache_hit_skips_adapter(tmp_path: Path) -> None:
    cache = comic_pdf.ComicPdfCache(tmp_path / "cache", max_bytes=10_000)
    cache.store(_downloaded_comic(tmp_path / "images"), _renderer())

    class Adapter:
        async def download_album(self, album_id: str, task_root: Path):
            raise AssertionError("cache hit must not download")

    async def scenario() -> None:
        service = comic_pdf.ComicPdfService(
            tmp_path / "jobs",
            cache_root=tmp_path / "cache",
            adapter_factory=lambda: Adapter(),
            renderer_factory=_renderer,
        )
        submission = await service.submit("1218951")
        assert submission.status == "cache_hit"
        assert (await submission.wait()).album_id == "1218951"

    asyncio.run(scenario())


def test_service_shutdown_fails_queued_and_active_requests(tmp_path: Path) -> None:
    async def scenario() -> None:
        gate = asyncio.Event()

        class Adapter:
            async def download_album(self, album_id: str, task_root: Path):
                await gate.wait()
                return _downloaded_comic(task_root, album_id)

        service = comic_pdf.ComicPdfService(
            tmp_path / "jobs",
            comic_pdf.ComicPdfConfig(max_concurrent_jobs=1, max_queued_jobs=2),
            cache_root=tmp_path / "cache",
            adapter_factory=lambda: Adapter(),
            renderer_factory=_renderer,
        )
        active = await service.submit("1001")
        queued = await service.submit("1002")
        await service.shutdown()
        with pytest.raises(comic_pdf.ComicPdfError, match="停止|取消"):
            await active.wait()
        with pytest.raises(comic_pdf.ComicPdfError, match="停止|取消"):
            await queued.wait()
        with pytest.raises(comic_pdf.ComicPdfError, match="停止"):
            await service.submit("1003")

    asyncio.run(scenario())


def test_encryptor_uses_full_jmid_and_cleanup_preserves_plain_cache(tmp_path: Path) -> None:
    pikepdf = pytest.importorskip("pikepdf")
    cache_dir = tmp_path / "cache" / "JM1218951-【作者】标题"
    cache_dir.mkdir(parents=True)
    source = cache_dir / f"{cache_dir.name}.pdf"
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        pdf.save(source)
    entry = comic_pdf.ComicCacheEntry(
        album_id="1218951",
        author="作者",
        title="标题",
        cache_dir=cache_dir,
        artifacts=(comic_pdf.ComicPdfArtifact(source, 1, (1,)),),
    )

    delivery = comic_pdf.PdfEncryptor(tmp_path / "temp").create_delivery(entry)

    assert delivery.password == "1218951"
    assert source.exists()
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(delivery.artifacts[0].path)
    with pikepdf.open(delivery.artifacts[0].path, password="1218951") as pdf:
        assert len(pdf.pages) == 1
    delivery.cleanup()
    assert not delivery.task_root.exists()
    assert source.exists()


def test_friend_route_prefers_capable_twin_before_claim() -> None:
    async def scenario() -> None:
        coordinator = comic_pdf.ComicFriendRouteCoordinator(wait_seconds=0.2)
        angel, demon = await asyncio.gather(
            coordinator.choose(
                "event-1",
                self_id="1443944862",
                is_friend=False,
                preferred_worker="1443944862",
            ),
            coordinator.choose(
                "event-1",
                self_id="2629227874",
                is_friend=True,
                preferred_worker="1443944862",
            ),
        )
        assert angel == demon
        assert demon.selected_worker == "2629227874"
        assert demon.has_friend is True

    asyncio.run(scenario())


def test_friend_route_keeps_preferred_worker_when_both_are_friends() -> None:
    async def scenario() -> None:
        coordinator = comic_pdf.ComicFriendRouteCoordinator(wait_seconds=0.2)
        decisions = await asyncio.gather(
            coordinator.choose(
                "event-2",
                self_id="1443944862",
                is_friend=True,
                preferred_worker="2629227874",
            ),
            coordinator.choose(
                "event-2",
                self_id="2629227874",
                is_friend=True,
                preferred_worker="2629227874",
            ),
        )
        assert all(item.selected_worker == "2629227874" for item in decisions)
        assert all(item.has_friend for item in decisions)

    asyncio.run(scenario())


def test_onebot_friend_lookup_accepts_direct_and_wrapped_results() -> None:
    class Api:
        def __init__(self, result) -> None:
            self.result = result

        async def call_api(self, action: str, **kwargs):
            assert action == "get_friend_list"
            return self.result

    assert asyncio.run(comic_pdf.is_onebot_friend(Api([{"user_id": 123}]), 123))
    assert asyncio.run(
        comic_pdf.is_onebot_friend(Api({"data": [{"user_id": "456"}]}), 456)
    )
    assert not asyncio.run(comic_pdf.is_onebot_friend(Api([]), 789))


def test_main_contract_uses_plain_jm_command_friend_route_and_unquoted_progress() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    assert 'JMCOMIC_DOWNLOAD_PATTERN = r"(?i)^jm\\s*([0-9]+)$"' in source
    assert "JM下载" not in source[source.index("async def jmcomic_download"):source.index("async def factorio_download")]
    assert "self._comic_friend_router.choose" in source
    assert "is_onebot_friend" in source
    assert "send_private_pdfs_with_password" in source
    handler_source = source[
        source.index("async def jmcomic_download"):source.index("async def factorio_download")
    ]
    assert "已私聊发送" not in handler_source
    assert "is_twin_bot_sender_id(sender_id)" in source
    assert "_comic_active_request_count" in source
    assert "你已有一个 JM 任务" not in handler_source
    assert "delivery.cleanup" in source
    assert (
        'event.stop_event()\n        claim_key = _command_claim_key(event, command_type="jmcomic_pdf")'
        not in handler_source
    )
    claim_index = handler_source.index(
        'claim_key = _command_claim_key(event, command_type="jmcomic_pdf")'
    )
    friend_lookup_index = handler_source.index(
        "current_is_friend = await is_onebot_friend"
    )
    worker_route_index = handler_source.index(
        "preferred = decide_migrated_command_route"
    )
    status_index = handler_source.index("yield event.plain_result(status_text)")
    assert "_chain_result_with_reply" not in handler_source
    assert "缓存命中，开始处理" in handler_source
    assert "开始下载，预计约" in handler_source
    assert "_comic_download_estimate_minutes" in handler_source
    stop_index = handler_source.rindex("event.stop_event()")
    assert claim_index < friend_lookup_index < worker_route_index < status_index < stop_index
