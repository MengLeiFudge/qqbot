from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.arc_apk_update_service import ArcApkUpdateManager


class FakeDownloader:
    def __init__(self, delay: float = 0.0, should_raise: bool = False) -> None:
        self.delay = delay
        self.should_raise = should_raise
        self.calls: list[str] = []

    def download_latest_apk(self, version: str, progress_callback=None):
        self.calls.append(version)
        if progress_callback is not None:
            progress_callback("10%（12.0 MiB / 120.0 MiB）")
        if self.delay:
            time.sleep(self.delay)
        if self.should_raise:
            raise RuntimeError("download boom")
        return type("Result", (), {"path": Path(f"D:/Games/Arcaea/arcaea_{version}.apk")})()


def test_arc_apk_update_manager_starts_download_and_reports_progress(tmp_path: Path) -> None:
    downloader = FakeDownloader(delay=0.1)
    manager = ArcApkUpdateManager(
        state_path=tmp_path / "run" / "data" / "arc" / "background_state.json",
        version_fetcher=lambda: "6.14.0c",
        downloader=downloader,
    )

    async def run() -> None:
        first = await manager.query_and_update()
        await asyncio.sleep(0.02)
        second = await manager.query_and_update()
        await asyncio.sleep(0.15)
        third = manager.render_status()

        assert "已开始下载" in first
        assert "当前进度：10%" in second
        assert "已下载完毕" in third
        assert downloader.calls == ["6.14.0c"]

    asyncio.run(run())


def test_arc_apk_update_manager_skips_already_downloaded_version(tmp_path: Path) -> None:
    state_path = tmp_path / "run" / "data" / "arc" / "background_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"version_last_downloaded": "6.14.0c"}', encoding="utf-8")
    downloader = FakeDownloader()
    manager = ArcApkUpdateManager(
        state_path=state_path,
        version_fetcher=lambda: "6.14.0c",
        downloader=downloader,
    )

    message = asyncio.run(manager.query_and_update())

    assert "安装包已经下载过" in message
    assert downloader.calls == []
