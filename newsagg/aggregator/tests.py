
from django.test import TestCase
from django.utils import timezone
from aggregator.models import NewsSource, NewsItem, MediaFile
from datetime import datetime


class NewsSourceModelTest(TestCase):
    """Тесты для модели NewsSource"""

    def setUp(self):
        self.source = NewsSource.objects.create(
            name="Test News Channel",
            username="test_channel",
            url="https://example.com/channel",
            source_type="telegram",
            is_active=True
        )

    def test_news_source_creation(self):
        """Проверка создания источника новостей"""
        self.assertEqual(self.source.name, "Test News Channel")
        self.assertEqual(self.source.username, "test_channel")
        self.assertTrue(self.source.is_active)
        self.assertEqual(self.source.source_type, "telegram")

    def test_news_source_str(self):
        """Проверка строкового представления"""
        self.assertEqual(str(self.source), "Test News Channel")


class NewsItemModelTest(TestCase):
    """Тесты для модели NewsItem"""

    def setUp(self):
        self.source = NewsSource.objects.create(
            name="Test Source",
            username="test_source",
            source_type="telegram"
        )

        self.news_item = NewsItem.objects.create(
            title="Test News Title",
            content="Test news content with some details",
            summary="Short summary",
            source=self.source,
            url="https://example.com/news/1",
            published_date=timezone.now(),
            media=True,
            media_type="image"
        )

    def test_news_item_creation(self):
        """Проверка создания новости"""
        self.assertEqual(self.news_item.title, "Test News Title")
        self.assertEqual(self.news_item.content, "Test news content with some details")
        self.assertEqual(self.news_item.source, self.source)
        self.assertTrue(self.news_item.media)
        self.assertEqual(self.news_item.media_type, "image")
        self.assertFalse(self.news_item.is_processed)

    def test_news_item_unique_url(self):
        """Проверка уникальности URL"""
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            NewsItem.objects.create(
                title="Another News",
                content="Different content",
                source=self.source,
                url="https://example.com/news/1",  # Дублирующий URL
                published_date=timezone.now()
            )

    def test_news_item_str_truncation(self):
        """Проверка усечения длинного заголовка"""
        long_title = "A" * 150
        news = NewsItem.objects.create(
            title=long_title,
            content="Content",
            source=self.source,
            url="https://example.com/news/2",
            published_date=timezone.now()
        )
        self.assertEqual(len(str(news)), 100)


class MediaFileModelTest(TestCase):
    """Тесты для модели MediaFile"""

    def setUp(self):
        self.source = NewsSource.objects.create(
            name="Test Source",
            username="test_source"
        )

        self.news = NewsItem.objects.create(
            title="News with media",
            content="Content",
            source=self.source,
            url="https://example.com/news/3",
            published_date=timezone.now()
        )

        self.media = MediaFile.objects.create(
            news=self.news,
            file_url="https://example.com/image.jpg",
            file_type="image",
            file_size=2097152  # 2 MB
        )

    def test_media_file_creation(self):
        """Проверка создания медиафайла"""
        self.assertEqual(self.media.news, self.news)
        self.assertEqual(self.media.file_type, "image")
        self.assertEqual(self.media.file_size, 2097152)

    def test_file_size_mb_property(self):
        """Проверка расчета размера в MB"""
        self.assertEqual(self.media.file_size_mb, 2.0)

    def test_is_image_property(self):
        """Проверка свойства is_image"""
        self.assertTrue(self.media.is_image)
        self.assertFalse(self.media.is_video)

    def test_is_video_property(self):
        """Проверка свойства is_video"""
        video = MediaFile.objects.create(
            news=self.news,
            file_url="https://example.com/video.mp4",
            file_type="video",
            file_size=10485760
        )
        self.assertTrue(video.is_video)
        self.assertFalse(video.is_image)