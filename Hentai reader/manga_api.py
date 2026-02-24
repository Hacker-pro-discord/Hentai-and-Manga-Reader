"""MangaDex API client for searching manga and fetching chapters/images."""

import requests
from typing import Optional
from dataclasses import dataclass


@dataclass
class MangaResult:
    id: str
    title: str
    description: str
    cover_url: str
    status: str
    year: Optional[int]
    tags: list[str]
    source: str = "mangadex"


@dataclass
class ChapterInfo:
    id: str
    chapter: str
    title: str
    volume: Optional[str]


class MangaDexAPI:
    BASE_URL = "https://api.mangadex.org"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "HentaiReader/1.0 (desktop app)"
        })

    def browse_manga(
        self,
        limit: int = 24,
        offset: int = 0,
        include_adult: bool = True
    ) -> tuple[list[MangaResult], int]:
        """Browse popular manga (no search). Returns (results, total_count)."""
        params = {
            "limit": min(limit * 2, 96),
            "offset": offset,
            "order[followedCount]": "desc",
            "includes[]": ["cover_art"],
            "contentRating[]": ["erotica", "pornographic"]
        }
        if not include_adult:
            params["contentRating[]"] = ["safe", "suggestive", "erotica", "pornographic"]
        r = self.session.get(f"{self.BASE_URL}/manga", params=params)
        r.raise_for_status()
        results, total = self._parse_manga_response(r.json(), limit)
        return results[:limit], total

    def search_manga(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        include_adult: bool = True
    ) -> tuple[list[MangaResult], int]:
        """Search manga by title. Returns (results, total_count)."""
        params = {
            "title": query,
            "limit": limit,
            "offset": offset,
            "order[followedCount]": "desc",
            "includes[]": ["cover_art"],
            "contentRating[]": ["erotica", "pornographic"]
        }
        if not include_adult:
            params["contentRating[]"] = ["safe", "suggestive", "erotica", "pornographic"]

        r = self.session.get(f"{self.BASE_URL}/manga", params=params)
        r.raise_for_status()
        return self._parse_manga_response(r.json(), limit)

    def _parse_manga_response(self, data: dict, limit: int) -> tuple[list[MangaResult], int]:
        results = []
        for item in data.get("data", []):
            if item.get("attributes", {}).get("isLocked"):
                continue
            attrs = item.get("attributes", {})
            titles = attrs.get("title") or {}
            title = titles.get("en") or (list(titles.values())[0] if titles else None)
            if not title:
                for alt in attrs.get("altTitles") or []:
                    if isinstance(alt, dict) and alt.get("en"):
                        title = alt["en"]
                        break
            title = title or "Unknown"
            desc = (attrs.get("description") or {}).get("en") or ""
            status = attrs.get("status", "unknown")
            year = attrs.get("year")
            cover_filename = None
            for rel in item.get("relationships", []):
                if rel.get("type") == "cover_art":
                    cover_filename = (rel.get("attributes") or {}).get("fileName")
                    if cover_filename:
                        break
            cover_url = ""
            if cover_filename:
                cover_url = f"https://uploads.mangadex.org/covers/{item['id']}/{cover_filename}.512.jpg"
            tags = []
            for tag in attrs.get("tags", []):
                name = (tag.get("attributes") or {}).get("name", {}).get("en")
                if name:
                    tags.append(name)
            results.append(MangaResult(
                id=item["id"],
                title=title,
                description=desc[:200] + "..." if len(desc) > 200 else desc,
                cover_url=cover_url,
                status=status,
                year=year,
                tags=tags[:5]
            ))
        total = data.get("total", len(results))
        return results, total

    def get_manga_chapters(
        self,
        manga_id: str,
        limit: int | None = None,
        lang: str = "en"
    ) -> list[ChapterInfo]:
        """Get ALL chapters for a manga (paginated). Pass limit=None for no limit."""
        chapters = self._fetch_all_chapters(manga_id, lang)
        if not chapters and lang != "ja":
            chapters = self._fetch_all_chapters(manga_id, "ja")
        if not chapters:
            chapters = self._fetch_all_chapters(manga_id, None)
        return chapters

    def _fetch_all_chapters(
        self, manga_id: str, lang: str | None
    ) -> list[ChapterInfo]:
        """Fetch all chapters via pagination."""
        all_chapters = []
        seen = set()
        limit = 100
        offset = 0

        while True:
            params = {
                "limit": limit,
                "offset": offset,
                "order[volume]": "asc",
                "order[chapter]": "asc",
            }
            if lang:
                params["translatedLanguage[]"] = [lang]
            r = self.session.get(f"{self.BASE_URL}/manga/{manga_id}/feed", params=params)
            r.raise_for_status()
            data = r.json()
            batch = data.get("data", [])
            if not batch:
                break
            for item in batch:
                attrs = item.get("attributes", {})
                ch = attrs.get("chapter") or "0"
                key = (attrs.get("volume") or "", ch)
                if key in seen:
                    continue
                seen.add(key)
                all_chapters.append(ChapterInfo(
                    id=item["id"],
                    chapter=ch,
                    title=attrs.get("title") or "",
                    volume=attrs.get("volume")
                ))
            if len(batch) < limit:
                break
            offset += limit

        def sort_key(c):
            try:
                return (float(c.volume or 0), float(c.chapter))
            except ValueError:
                return (0, 0)
        return sorted(all_chapters, key=sort_key)

    def get_chapter_images(self, chapter_id: str) -> list[str]:
        """Get image URLs for a chapter. Uses uploads.mangadex.org for reliability."""
        r = self.session.get(f"{self.BASE_URL}/at-home/server/{chapter_id}")
        r.raise_for_status()
        data = r.json()
        ch_data = data["chapter"]
        hash_val = ch_data["hash"]
        filenames = ch_data.get("dataSaver") or ch_data.get("data", [])
        if not filenames:
            return []
        base = "https://uploads.mangadex.org"
        quality = "data-saver" if ch_data.get("dataSaver") else "data"
        return [f"{base}/{quality}/{hash_val}/{f}" for f in filenames]

    def get_chapter_url(self, chapter_id: str) -> str:
        """Get MangaDex web reader URL for a chapter."""
        return f"https://mangadex.org/chapter/{chapter_id}"

    def fetch_image(self, url: str) -> bytes:
        """Download image bytes."""
        headers = {
            "Referer": "https://mangadex.org/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        r = self.session.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        if b"<!doctype" in r.content[:50].lower() or b"<html" in r.content[:50].lower():
            raise ValueError("Server returned HTML instead of image")
        return r.content
