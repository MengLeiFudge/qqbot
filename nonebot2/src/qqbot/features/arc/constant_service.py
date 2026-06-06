from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from qqbot.features.arc.alias_service import EN_WIKI_API_URL

DIFFICULTY_CC_FIELDS = {
    "Past": 0,
    "Present": 1,
    "Future": 2,
    "Beyond": 3,
    "Eternal": 4,
}


def fetch_en_wiki_wikitext(title: str) -> str:
    query = urlencode(
        {
            "action": "query",
            "titles": title,
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "format": "json",
        }
    )
    request = Request(
        f"{EN_WIKI_API_URL}?{query}",
        headers={"User-Agent": "qqbot/0.1"},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    pages = payload.get("query", {}).get("pages", {})
    for page in pages.values():
        revisions = page.get("revisions") or []
        if not revisions:
            continue
        revision = revisions[0]
        return str(revision.get("slots", {}).get("main", {}).get("*") or revision.get("*") or "")
    return ""


class ArcConstantService:
    def __init__(self, cache_path: Path, wiki_text_fetcher=None) -> None:
        self.cache_path = Path(cache_path)
        self.wiki_text_fetcher = wiki_text_fetcher or fetch_en_wiki_wikitext

    def sync_constant_cache(self, songs: list[dict[str, str]], now: datetime | None = None) -> dict:
        current = now or datetime.now()
        payload = {"updated_at": current.isoformat(), "songs": {}}
        for song in songs:
            song_id = str(song.get("id", "")).strip()
            title = str(song.get("title", "")).strip()
            if not song_id or not title:
                continue
            try:
                wikitext = self.wiki_text_fetcher(title)
            except Exception:
                wikitext = ""
            payload["songs"][song_id] = {
                "title": title,
                "constants": self.parse_constants(wikitext),
            }
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload

    def sync_missing_constants(
        self,
        songs: list[dict[str, str]],
        now: datetime | None = None,
        limit: int = 20,
    ) -> dict:
        current = now or datetime.now()
        payload = self.load_constant_cache()
        payload.setdefault("songs", {})
        synced_count = 0
        for song in songs:
            song_id = str(song.get("id", "")).strip()
            title = str(song.get("title", "")).strip()
            if not song_id or not title:
                continue
            existing = payload["songs"].get(song_id)
            if existing and existing.get("constants"):
                continue
            if synced_count >= limit:
                break
            try:
                wikitext = self.wiki_text_fetcher(title)
            except Exception:
                wikitext = ""
            payload["songs"][song_id] = {
                "title": title,
                "constants": self.parse_constants(wikitext),
            }
            synced_count += 1
        payload["updated_at"] = current.isoformat()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload

    def load_constant_cache(self) -> dict:
        if not self.cache_path.exists():
            return {"updated_at": "", "songs": {}}
        return json.loads(self.cache_path.read_text(encoding="utf-8"))

    def parse_constants(self, wikitext: str) -> dict[str, float]:
        constants: dict[str, float] = {}
        for field_name, difficulty_index in DIFFICULTY_CC_FIELDS.items():
            match = re.search(
                rf"\|\s*{re.escape(field_name)}\s+CC\s*=\s*([0-9]+(?:\.[0-9]+)?)",
                wikitext,
                flags=re.IGNORECASE,
            )
            if match is not None:
                constants[str(difficulty_index)] = float(match.group(1))
        return constants
