import re
from typing import List, Dict, Optional

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.utils import timezone
from datetime import datetime, timezone as dt_timezone

from .base_parser import BaseParser


class RSSParser(BaseParser):
    """Парсер RSS-лент с fallback-обработкой битых XML, кодировок и медиа."""

    def __init__(self, source):
        super().__init__(source)
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        """Сессия с retry для более стабильной загрузки RSS."""
        session = requests.Session()

        retries = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
        )

        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def parse(self) -> List[Dict]:
        try:
            print(f"Парсим RSS: {self.source.name}")

            raw_feed = self._fetch_feed()
            if raw_feed is None:
                return []

            feed = self._parse_feed(raw_feed)
            if feed is None:
                return []

            if getattr(feed, "bozo", False):
                print(f"Предупреждение RSS для {self.source.name}: {feed.bozo_exception}")

            news_items = []
            entries = getattr(feed, "entries", []) or []

            for entry in entries[:25]:
                try:
                    url = self._safe_get(entry, "link", default="")
                    if not url:
                        continue

                    content = self._get_content(entry)
                    media_items = self._extract_media(entry, content)

                    news_data = {
                        "title": self._safe_get(entry, "title", default="Без заголовка"),
                        "content": content,
                        "url": url,
                        "published_date": self._parse_date(entry),
                        "summary": "",  # summary теперь генерируется LLM
                        "media": bool(media_items),
                        "media_type": media_items[0]["type"] if media_items else "none",
                        "media_items": media_items,
                    }

                    news_items.append(news_data)

                except Exception as e:
                    print(f"Ошибка обработки новости в {self.source.name}: {e}")
                    continue

            print(f"RSS {self.source.name}: найдено {len(news_items)} новостей")
            return news_items

        except Exception as e:
            print(f"Критическая ошибка RSS парсинга {self.source.name}: {e}")
            return []

    def _fetch_feed(self) -> Optional[bytes]:
        """Скачать RSS как bytes, чтобы не упереться в проблемы encoding/SSL."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": "ru,en;q=0.9",
            "Cache-Control": "no-cache",
        }

        try:
            response = self.session.get(
                self.source.url,
                headers=headers,
                timeout=(10, 30),
                allow_redirects=True,
            )
            response.raise_for_status()
            return response.content

        except requests.exceptions.SSLError as e:
            print(f"SSL ошибка для {self.source.name}: {e}")
            try:
                response = self.session.get(
                    self.source.url,
                    headers=headers,
                    timeout=(10, 30),
                    allow_redirects=True,
                    verify=False,
                )
                response.raise_for_status()
                return response.content
            except Exception as e2:
                print(f"Не удалось скачать RSS {self.source.name} даже с verify=False: {e2}")
                return None

        except Exception as e:
            print(f"Ошибка загрузки RSS {self.source.name}: {e}")
            return None

    def _parse_feed(self, raw_feed: bytes):
        """
        Пытаемся распарсить RSS несколькими способами:
        1) bytes напрямую
        2) utf-8 текст
        3) fallback по очистке XML
        """
        try:
            feed = feedparser.parse(raw_feed)
            if getattr(feed, "entries", None):
                return feed
        except Exception:
            pass

        try:
            text = raw_feed.decode("utf-8", errors="replace")
            text = self._sanitize_xml(text)
            feed = feedparser.parse(text)
            if getattr(feed, "entries", None):
                return feed
        except Exception:
            pass

        try:
            text = raw_feed.decode("utf-8", errors="replace")
            text = self._sanitize_xml(text)
            feed = feedparser.parse(text)
            return feed
        except Exception as e:
            print(f"Не удалось распарсить RSS {self.source.name}: {e}")
            return None

    def _sanitize_xml(self, text: str) -> str:
        """Убираем частые проблемы XML."""
        text = text.replace("\x00", "")
        text = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F]", "", text)
        return text

    def _safe_get(self, entry, key: str, default: str = "") -> str:
        try:
            value = getattr(entry, key, default)
            if value is None:
                return default
            return str(value)
        except Exception:
            return default

    def _get_content(self, entry) -> str:
        """Получаем полный текст новости максимально устойчиво."""
        try:
            if hasattr(entry, "content") and entry.content:
                first = entry.content[0]
                if hasattr(first, "value") and first.value:
                    return str(first.value)
        except Exception:
            pass

        try:
            if hasattr(entry, "summary_detail") and entry.summary_detail:
                if isinstance(entry.summary_detail, dict):
                    value = entry.summary_detail.get("value")
                    if value:
                        return str(value)
                elif hasattr(entry.summary_detail, "value"):
                    value = entry.summary_detail.value
                    if value:
                        return str(value)
        except Exception:
            pass

        try:
            if hasattr(entry, "summary") and entry.summary:
                return str(entry.summary)
        except Exception:
            pass

        try:
            if hasattr(entry, "description") and entry.description:
                return str(entry.description)
        except Exception:
            pass

        return ""

    def _parse_date(self, entry) -> datetime:
        """Парсим дату публикации."""
        date_fields = [
            "published_parsed",
            "updated_parsed",
            "created_parsed",
            "modified_parsed",
        ]

        for field in date_fields:
            try:
                value = getattr(entry, field, None)

                if value:
                    return datetime(
                        *value[:6],
                        tzinfo=dt_timezone.utc
                    )

            except Exception:
                continue

        return timezone.now()

    def _extract_media(self, entry, content: str = "") -> List[Dict]:
        """
        Возвращает список медиа-объектов из RSS entry.
        Каждый элемент:
        {
            "url": "...",
            "type": "image|video|audio|document"
        }
        """
        media_items = []

        # 1) enclosures
        try:
            if hasattr(entry, "enclosures") and entry.enclosures:
                for enclosure in entry.enclosures:
                    url = enclosure.get("href") if isinstance(enclosure, dict) else getattr(enclosure, "href", "")
                    mime = enclosure.get("type", "") if isinstance(enclosure, dict) else getattr(enclosure, "type", "")

                    if not url:
                        continue

                    media_items.append({
                        "url": url,
                        "type": self._mime_to_type(mime),
                    })
        except Exception:
            pass

        # 2) media_content
        try:
            if hasattr(entry, "media_content") and entry.media_content:
                for media in entry.media_content:
                    url = media.get("url") if isinstance(media, dict) else getattr(media, "url", "")
                    mime = media.get("type", "") if isinstance(media, dict) else getattr(media, "type", "")

                    if not url:
                        continue

                    media_items.append({
                        "url": url,
                        "type": self._mime_to_type(mime),
                    })
        except Exception:
            pass

        # 3) media_thumbnail
        try:
            if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                for thumb in entry.media_thumbnail:
                    url = thumb.get("url") if isinstance(thumb, dict) else getattr(thumb, "url", "")
                    if url:
                        media_items.append({
                            "url": url,
                            "type": "image",
                        })
        except Exception:
            pass

        # 4) links with rel=enclosure
        try:
            if hasattr(entry, "links") and entry.links:
                for link in entry.links:
                    if not isinstance(link, dict):
                        continue

                    rel = (link.get("rel") or "").lower()
                    href = link.get("href", "")
                    mime = link.get("type", "")

                    if rel == "enclosure" and href:
                        media_items.append({
                            "url": href,
                            "type": self._mime_to_type(mime),
                        })
        except Exception:
            pass

        # 5) fallback: первая картинка из HTML content/summary
        try:
            html_source = content or ""
            if not html_source and hasattr(entry, "summary"):
                html_source = str(entry.summary or "")

            if html_source:
                img_match = re.search(
                    r'<img[^>]+src=["\']([^"\']+)["\']',
                    html_source,
                    flags=re.IGNORECASE
                )
                if img_match:
                    media_items.append({
                        "url": img_match.group(1),
                        "type": "image",
                    })
        except Exception:
            pass

        # убрать дубликаты по url
        seen = set()
        unique_media = []
        for item in media_items:
            url = item.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            unique_media.append(item)

        return unique_media

    def _mime_to_type(self, mime: str) -> str:
        mime = (mime or "").lower()
        if "image" in mime:
            return "image"
        if "video" in mime:
            return "video"
        if "audio" in mime:
            return "audio"
        if "pdf" in mime or "document" in mime:
            return "document"
        return "document"