from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener


LATEST_RELEASES_URL = "https://factorio.com/api/latest-releases"
DOWNLOAD_URL_TEMPLATE = "https://www.factorio.com/get-download/{version}/expansion/win64"
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class FactorioCredentials:
    username: str
    token: str


@dataclass(frozen=True, slots=True)
class FactorioDownloadLink:
    version: str
    url: str


class FactorioDownloadError(RuntimeError):
    """可直接转成用户提示的 Factorio 下载链接获取错误。"""


class _HttpClient(Protocol):
    def get_json(self, url: str, timeout: float) -> dict: ...

    def resolve_redirect(self, url: str, timeout: float) -> str: ...


class FactorioHttpClient:
    def get_json(self, url: str, timeout: float) -> dict:
        request = Request(url, headers={"User-Agent": _user_agent()})
        try:
            with build_opener().open(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise FactorioDownloadError(f"Factorio 版本接口返回 HTTP {exc.code}") from exc
        except URLError as exc:
            raise FactorioDownloadError(f"无法连接 Factorio 版本接口：{exc.reason}") from exc
        except TimeoutError as exc:
            raise FactorioDownloadError("连接 Factorio 版本接口超时") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FactorioDownloadError("Factorio 版本接口返回内容不是 JSON") from exc
        if not isinstance(data, dict):
            raise FactorioDownloadError("Factorio 版本接口返回结构异常")
        return data

    def resolve_redirect(self, url: str, timeout: float) -> str:
        request = Request(url, headers={"User-Agent": _user_agent()})
        try:
            with build_opener(_NoRedirectHandler()).open(request, timeout=timeout) as response:
                if 200 <= response.status < 300:
                    return response.url
                raise FactorioDownloadError(f"Factorio 下载接口返回 HTTP {response.status}")
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("Location", "").strip()
                if location:
                    return urljoin(url, location)
            if exc.code in {401, 403}:
                raise FactorioDownloadError("Factorio 凭据无效或账号没有 Space Age 下载权限") from exc
            if exc.code == 404:
                raise FactorioDownloadError("Factorio 官网没有提供当前版本的 Space Age Windows 安装包") from exc
            raise FactorioDownloadError(f"Factorio 下载接口返回 HTTP {exc.code}") from exc
        except URLError as exc:
            raise FactorioDownloadError(f"无法连接 Factorio 下载接口：{exc.reason}") from exc
        except TimeoutError as exc:
            raise FactorioDownloadError("连接 Factorio 下载接口超时") from exc


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


class FactorioDownloadService:
    def __init__(
        self,
        http_client: _HttpClient | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        credentials: FactorioCredentials | None = None,
    ) -> None:
        self.http_client = http_client or FactorioHttpClient()
        self.timeout_seconds = timeout_seconds
        self._credentials = credentials

    def fetch_space_age_windows_link(self) -> FactorioDownloadLink:
        credentials = self._credentials or load_factorio_credentials()
        version = self._fetch_stable_space_age_version()
        url = build_factorio_download_url(version, credentials)
        resolved_url = self.http_client.resolve_redirect(url, self.timeout_seconds)
        if not resolved_url:
            raise FactorioDownloadError("Factorio 下载接口没有返回下载地址")
        if _contains_secret(resolved_url, credentials):
            raise FactorioDownloadError("Factorio 下载接口返回了包含 token 的地址，已拒绝发送")
        return FactorioDownloadLink(version=version, url=resolved_url)

    def _fetch_stable_space_age_version(self) -> str:
        data = self.http_client.get_json(LATEST_RELEASES_URL, self.timeout_seconds)
        stable = data.get("stable")
        if not isinstance(stable, dict):
            raise FactorioDownloadError("Factorio 版本接口缺少 stable 字段")
        version = stable.get("expansion")
        if not isinstance(version, str) or not version.strip():
            raise FactorioDownloadError("Factorio 版本接口缺少 stable.expansion 版本号")
        return version.strip()


def load_factorio_credentials(env: dict[str, str] | None = None) -> FactorioCredentials:
    source = os.environ if env is None else env
    username = source.get("FACTORIO_USERNAME", "").strip()
    token = source.get("FACTORIO_TOKEN", "").strip()
    if not username or not token:
        raise FactorioDownloadError("缺少 FACTORIO_USERNAME 或 FACTORIO_TOKEN")
    return FactorioCredentials(username=username, token=token)


def build_factorio_download_url(version: str, credentials: FactorioCredentials) -> str:
    query = urlencode({"username": credentials.username, "token": credentials.token})
    return f"{DOWNLOAD_URL_TEMPLATE.format(version=version)}?{query}"


def render_factorio_download_link_message(link: FactorioDownloadLink) -> str:
    return (
        f"Factorio: Space Age Windows 安装包下载链接（{link.version}）：\n"
        f"{link.url}\n"
        "链接有时效性，失效后请重新发送下载链接指令。"
    )


def _contains_secret(url: str, credentials: FactorioCredentials) -> bool:
    return credentials.token in url


def _user_agent() -> str:
    return "qqbot-factorio-download-link/1.0"
