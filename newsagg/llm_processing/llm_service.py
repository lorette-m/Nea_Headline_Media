import json
import logging
import re
from typing import Any, Dict, List

import requests
from django.db import transaction
from django.utils import timezone

from aggregator.models import NewsItem, Tag, NewsItemTag

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b-instruct"

CYRILLIC_TAG_RE = re.compile(r"^[А-Яа-яЁё0-9\s\-]+$")


def ask_llm(prompt: str) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def _build_prompt(news: NewsItem) -> str:
    text = (news.content or "").strip()
    title = (news.title or "").strip()

    return f"""
Ты анализируешь новостной текст.

Верни ТОЛЬКО JSON строго в таком формате:
{{
  "summary": "подробное краткое изложение",
  "tags": ["тег1", "тег2"]
}}

Правила для summary:
- обязательно пиши только на русском языке
- без иероглифов
- 2–4 предложения
- не повторяй заголовок дословно
- не делай summary слишком коротким
- объясняй суть, контекст и возможные последствия
- не используй markdown
- без пояснений вокруг JSON

Правила для tags:
- только русские теги
- только кириллица, цифры и дефис
- максимум 5 тегов
- теги короткие
- без иностранных слов
- без английских букв и других алфавитов
- без дубликатов

Заголовок:
{title}

Текст:
{text if text else title}
""".strip()


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])

    raise ValueError("LLM response does not contain valid JSON")


def _normalize_tags(tags: Any) -> List[str]:
    if not isinstance(tags, list):
        return []

    normalized = []
    seen = set()

    for tag in tags:
        tag_name = str(tag).strip().lower()
        tag_name = re.sub(r"\s+", " ", tag_name)

        if not tag_name:
            continue

        if not re.search(r"[А-Яа-яЁё]", tag_name):
            continue

        if not CYRILLIC_TAG_RE.match(tag_name):
            continue

        if tag_name in seen:
            continue

        seen.add(tag_name)
        normalized.append(tag_name)

    return normalized[:5]


@transaction.atomic
def process_news(news: NewsItem) -> bool:
    try:
        news.processing_status = "processing"
        news.processing_started_at = timezone.now()
        news.processing_error = ""
        news.save(update_fields=["processing_status", "processing_started_at", "processing_error"])

        prompt = _build_prompt(news)
        result = ask_llm(prompt)
        data = _extract_json(result)

        summary = str(data.get("summary", "")).strip()
        tags = _normalize_tags(data.get("tags", []))

        if summary:
            news.summary = summary

        news.is_processed = True
        news.processing_status = "processed"
        news.processed_at = timezone.now()
        news.save(
            update_fields=[
                "summary",
                "is_processed",
                "processing_status",
                "processed_at",
            ]
        )

        for tag_name in tags:
            tag, _ = Tag.objects.get_or_create(name=tag_name)
            NewsItemTag.objects.get_or_create(news=news, tag=tag)

        logger.info("Новость %s успешно обработана LLM", news.id)
        return True

    except Exception as e:
        logger.error("Ошибка LLM обработки новости %s: %s", news.id, e)

        news.is_processed = False
        news.processing_status = "failed"
        news.processing_error = str(e)
        news.processed_at = timezone.now()
        news.save(
            update_fields=[
                "is_processed",
                "processing_status",
                "processing_error",
                "processed_at",
            ]
        )
        return False