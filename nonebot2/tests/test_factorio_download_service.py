from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.factorio_download_service import (
    FactorioCredentials,
    FactorioDownloadError,
    FactorioDownloadLink,
    FactorioDownloadService,
    build_factorio_download_url,
    load_factorio_credentials,
    render_factorio_download_link_message,
)


class FakeHttpClient:
    def __init__(self, data: dict, redirect_url: str) -> None:
        self.data = data
        self.redirect_url = redirect_url
        self.json_urls: list[str] = []
        self.redirect_urls: list[str] = []

    def get_json(self, url: str, timeout: float) -> dict:
        self.json_urls.append(url)
        return self.data

    def resolve_redirect(self, url: str, timeout: float) -> str:
        self.redirect_urls.append(url)
        return self.redirect_url


def test_load_factorio_credentials_reads_required_env() -> None:
    credentials = load_factorio_credentials(
        {"FACTORIO_USERNAME": "MengLei", "FACTORIO_TOKEN": "secret-token"}
    )

    assert credentials == FactorioCredentials("MengLei", "secret-token")


def test_load_factorio_credentials_rejects_missing_values() -> None:
    with pytest.raises(FactorioDownloadError, match="FACTORIO_USERNAME"):
        load_factorio_credentials({})


def test_build_factorio_download_url_uses_space_age_windows_target() -> None:
    url = build_factorio_download_url(
        "2.0.76",
        FactorioCredentials("Meng Lei", "a+b"),
    )

    assert url.startswith("https://www.factorio.com/get-download/2.0.76/expansion/win64?")
    assert "username=Meng+Lei" in url
    assert "token=a%2Bb" in url


def test_fetch_space_age_windows_link_resolves_fresh_redirect() -> None:
    http_client = FakeHttpClient(
        data={"stable": {"expansion": "2.0.76"}},
        redirect_url="https://cdn.factorio.com/releases/factorio-space-age-2.0.76-win64.exe?ttl=1",
    )
    service = FactorioDownloadService(
        http_client=http_client,
        credentials=FactorioCredentials("MengLei", "secret-token"),
    )

    link = service.fetch_space_age_windows_link()

    assert link.version == "2.0.76"
    assert link.url.endswith("factorio-space-age-2.0.76-win64.exe?ttl=1")
    assert http_client.redirect_urls == [
        "https://www.factorio.com/get-download/2.0.76/expansion/win64?username=MengLei&token=secret-token"
    ]


def test_fetch_space_age_windows_link_rejects_secret_bearing_redirect() -> None:
    service = FactorioDownloadService(
        http_client=FakeHttpClient(
            data={"stable": {"expansion": "2.0.76"}},
            redirect_url=(
                "https://www.factorio.com/get-download/2.0.76/expansion/win64"
                "?username=MengLei&token=secret-token"
            ),
        ),
        credentials=FactorioCredentials("MengLei", "secret-token"),
    )

    with pytest.raises(FactorioDownloadError, match="包含 token"):
        service.fetch_space_age_windows_link()


def test_fetch_space_age_windows_link_requires_stable_expansion_version() -> None:
    service = FactorioDownloadService(
        http_client=FakeHttpClient(data={"stable": {}}, redirect_url="unused"),
        credentials=FactorioCredentials("MengLei", "secret-token"),
    )

    with pytest.raises(FactorioDownloadError, match="stable.expansion"):
        service.fetch_space_age_windows_link()


def test_render_factorio_download_link_message_avoids_group_direct_link() -> None:
    message = render_factorio_download_link_message(
        FactorioDownloadLink(version="2.0.76", url="https://cdn.example/f.exe")
    )

    assert "Factorio: Space Age Windows" in message
    assert "2.0.76" in message
    assert "官网账号下载页" in message
    assert "https://cdn.example/f.exe" not in message
    assert "失效后请重新发送" not in message
