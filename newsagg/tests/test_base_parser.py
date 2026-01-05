from django.test import TestCase
from django.utils import timezone
from aggregator.models import NewsSource, NewsItem
from aggregator.parsers.base_parser import BaseParser
from unittest.mock import Mock


class TestParser(BaseParser):
    """Тестовая реализация абстрактного парсера"""

    def __init__(self, source):
        super().__init__(source)
        self.name = "TestParser"

    def parse(self):
        return [
            {
                "title": "Test News",
                "content": "Test content",
                "url": "https://example.com/news/test",
                "published_date": timezone.now(),
                "summary": "Test summary"
            }
        ]


class BaseParserTest(TestCase):
    """Тесты для базового парсера"""

    def setUp(self):
        self.source = NewsSource.objects.create(
            name="Test Parser Source",
            username="test_parser",
            source_type="telegram"
        )
        self.parser = TestParser(self.source)

    def test_clean_text(self):
        """Проверка очистки текста"""
        text = "  Много    пробелов   между   словами  "
        cleaned = self.parser.clean_text(text)
        self.assertEqual(cleaned, "Много пробелов между словами")

    def test_clean_text_empty(self):
        """Проверка очистки пустого текста"""
        self.assertEqual(self.parser.clean_text(""), "")
        self.assertEqual(self.parser.clean_text(None), "")

    def test_clean_text_with_newlines(self):
        """Проверка очистки текста с переносами строк"""
        text = "Строка1\n\nСтрока2\n\n\nСтрока3"
        cleaned = self.parser.clean_text(text)
        self.assertEqual(cleaned, "Строка1 Строка2 Строка3")

    def test_save_news_item_success(self):
        """Проверка успешного сохранения новости"""
        news_data = {
            "title": "New Article",
            "content": "Article content",
            "url": "https://example.com/article/1",
            "published_date": timezone.now(),
            "summary": "Brief summary",
            "media": False,
            "media_type": "none"
        }

        news_item = self.parser.save_news_item(news_data)

        self.assertIsNotNone(news_item)
        self.assertEqual(news_item.title, "New Article")
        self.assertEqual(news_item.source, self.source)
        self.assertEqual(NewsItem.objects.count(), 1)

    def test_save_news_item_duplicate(self):
        """Проверка отклонения дубликата новости"""
        news_data = {
            "title": "Duplicate Article",
            "content": "Content",
            "url": "https://example.com/duplicate",
            "published_date": timezone.now()
        }

        # Первое сохранение
        first_save = self.parser.save_news_item(news_data)
        self.assertIsNotNone(first_save)

        # Попытка сохранить дубликат
        duplicate_save = self.parser.save_news_item(news_data)
        self.assertIsNone(duplicate_save)

        # В базе должна быть только одна новость
        self.assertEqual(NewsItem.objects.count(), 1)

    def test_save_news_item_with_media(self):
        """Проверка сохранения новости с медиа"""
        news_data = {
            "title": "Article with Image",
            "content": "Content with media",
            "url": "https://example.com/media/1",
            "published_date": timezone.now(),
            "media": True,
            "media_type": "image"
        }

        news_item = self.parser.save_news_item(news_data)

        self.assertTrue(news_item.media)
        self.assertEqual(news_item.media_type, "image")