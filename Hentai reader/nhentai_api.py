"""NHentai API client - adult doujinshi/manga source."""

import requests
from typing import Optional
from dataclasses import dataclass, field

from manga_api import MangaResult, ChapterInfo


# Image extension from NHentai type: j=jpg, p=png, g=gif
_EXT = {"j": "jpg", "p": "png", "g": "gif"}


class NHentaiAPI:
    """NHentai.net API - galleries are single complete works (no chapters)."""

    BASE = "https://nhentai.net/api"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://nhentai.net/",
        })

    def browse_manga(
        self,
        limit: int = 24,
        offset: int = 0,
        include_adult: bool = True,
    ) -> tuple[list[MangaResult], int]:
        """Browse popular galleries (all NHentai is adult)."""
        return self.search_manga("", limit=limit, offset=offset, include_adult=True)

    def search_manga(
        self,
        query: str,
        limit: int = 24,
        offset: int = 0,
        include_adult: bool = True,
    ) -> tuple[list[MangaResult], int]:
        """Search galleries. All NHentai is adult."""
        page = (offset // 25) + 1
        params = {"page": page, "sort": "popular"}
        if query:
            params["query"] = query
        else:
            params["query"] = "all"  # Empty browse uses "all" to list galleries
        try:
            r = self.session.get(
                f"{self.BASE}/galleries/search",
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise RuntimeError(f"NHentai search failed: {e}") from e

        result = data.get("result", [])
        num_pages = data.get("num_pages", 1)
        per_page = data.get("per_page", 25)
        total = num_pages * per_page
        results = [self._to_manga(g) for g in result[:limit]]
        return results, total

    def _to_manga(self, g: dict) -> MangaResult:
        gid = str(g.get("id", ""))
        title_obj = g.get("title", {}) or {}
        title = title_obj.get("english") or title_obj.get("japanese") or f"Gallery {gid}"
        media_id = g.get("media_id", "")
        cover_ext = "jpg"
        if g.get("images", {}).get("cover"):
            cover_ext = _EXT.get(g["images"]["cover"].get("t", "j"), "jpg")
        cover_url = f"https://t.nhentai.net/galleries/{media_id}/cover.{cover_ext}"

        tags = []
        for t in g.get("tags", [])[:5]:
            n = t.get("name")
            if isinstance(n, dict):
                name = n.get("english") or n.get("japanese") or (list(n.values())[0] if n else None)
            else:
                name = n
            if isinstance(name, str):
                tags.append(name)

        return MangaResult(
            source="nhentai",
            id=gid,
            title=title[:80] + "..." if len(title) > 80 else title,
            description="",
            cover_url=cover_url,
            status="completed",
            year=None,
            tags=tags,
        )

    def get_manga_chapters(
        self,
        manga_id: str,
        limit: int | None = None,
        lang: str = "en",
    ) -> list[ChapterInfo]:
        """NHentai galleries are single works - return one 'chapter'."""
        return [ChapterInfo(id=manga_id, chapter="1", title="", volume=None)]

    def get_chapter_images(self, chapter_id: str) -> list[str]:
        """Get image URLs for a gallery (chapter_id = gallery id)."""
        try:
            r = self.session.get(f"{self.BASE}/gallery/{chapter_id}", timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []

        media_id = str(data.get("media_id", ""))
        pages = data.get("images", {}).get("pages", [])
        urls = []
        for i, p in enumerate(pages):
            ext = _EXT.get(p.get("t", "j"), "jpg")
            urls.append(f"https://i.nhentai.net/galleries/{media_id}/{i + 1}.{ext}")
        return urls

    def fetch_image(self, url: str) -> bytes:
        """Download image bytes."""
        r = self.session.get(url, headers={"Referer": "https://nhentai.net/"}, timeout=30)
        r.raise_for_status()
        if b"<!doctype" in r.content[:50].lower() or b"<html" in r.content[:50].lower():
            raise ValueError("Server returned HTML instead of image")
        return r.content
