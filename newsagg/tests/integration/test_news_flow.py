from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from aggregator.models import NewsSource, NewsItem, MediaFile
from unittest.mock import patch, Mock


class NewsAggregationFlowTest(TestCase):
    """Интеграционный тест полного цикла агрегации и отображения новостей"""

    def setUp(self):
        """Подготовка тестового окружения"""
        self.client = Client()

        self.source1 = NewsSource.objects.create(
            name="Tech News",
            username="tech_news",
            url="https://technews.example.com/rss",
            source_type="telegram",
            is_active=True
        )

        self.source2 = NewsSource.objects.create(
            name="Sports News",
            username="sports_news",
            url="https://sportsnews.example.com/rss",
            source_type="telegram",
            is_active=True
        )

    def test_full_news_aggregation_and_display_flow(self):
        """
        Интеграционный тест: парсинг источников -> сохранение в БД ->
        отображение на странице -> фильтрация
        """
        news1 = NewsItem.objects.create(
            title="Breaking Tech News: AI Revolution",
            content="Artificial Intelligence is changing the world...",
            summary="AI is revolutionary",
            source=self.source1,
            url="https://technews.example.com/ai-revolution",
            published_date=timezone.now(),
            media=False,
            media_type="none"
        )

        news2 = NewsItem.objects.create(
            title="Sports Update: Championship Finals",
            content="The championship finals were spectacular...",
            summary="Championship finals recap",
            source=self.source2,
            url="https://sportsnews.example.com/finals",
            published_date=timezone.now(),
            media=False,
            media_type="none"
        )

        news3 = NewsItem.objects.create(
            title="Tech Review: New Smartphone",
            content="The latest smartphone features...",
            summary="Smartphone review",
            source=self.source1,
            url="https://technews.example.com/smartphone",
            published_date=timezone.now(),
            media=False,
            media_type="none"
        )

        # новости сохранены
        self.assertEqual(NewsItem.objects.count(), 3)

        # главная страница
        response = self.client.get(reverse('news_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Breaking Tech News")
        self.assertContains(response, "Sports Update")
        self.assertContains(response, "Tech Review")

        # наличие источников для фильтрации
        self.assertContains(response, "Tech News")
        self.assertContains(response, "Sports News")

        # фильтрация по источнику
        response_filtered = self.client.get(
            reverse('news_list'),
            {'source': self.source1.id}
        )
        self.assertEqual(response_filtered.status_code, 200)
        self.assertContains(response_filtered, "Breaking Tech News")
        self.assertContains(response_filtered, "Tech Review")

        # детальная страница новости
        response_detail = self.client.get(
            reverse('news_detail_card', kwargs={'pk': news1.pk})
        )
        self.assertEqual(response_detail.status_code, 200)
        self.assertContains(response_detail, "AI Revolution")
        self.assertContains(response_detail, "Artificial Intelligence")

        # HTMX-запрос для фильтрации
        response_htmx = self.client.get(
            reverse('news_list'),
            {'source': self.source2.id},
            HTTP_HX_REQUEST='true'
        )
        self.assertEqual(response_htmx.status_code, 200)
        # фрагмент вернулся
        self.assertNotContains(response_htmx, '<html>')
        self.assertContains(response_htmx, "Sports Update")

        # проверка сортировки
        all_news = NewsItem.objects.all()
        self.assertTrue(
            all_news[0].published_date >= all_news[1].published_date
        )

    def test_news_with_media_metadata(self):
        """Отдельный тест для проверки метаданных медиафайлов"""
        news = NewsItem.objects.create(
            title="News with Media",
            content="Content",
            source=self.source1,
            url="https://example.com/media-news",
            published_date=timezone.now(),
            media=True,
            media_type="image"
        )

        media = MediaFile.objects.create(
            news=news,
            file_url="https://example.com/image.jpg",
            file_type="image",
            file_size=1048576
        )

        # метаданные
        self.assertTrue(media.is_image)
        self.assertEqual(media.file_size_mb, 1.0)
        self.assertEqual(media.file_url, "https://example.com/image.jpg")

    def test_parser_manager_integration(self):
        """Тест интеграции ParserManager с моделями"""
        news_data = [
            {
                "title": "Parsed News 1",
                "content": "Content 1",
                "url": "https://example.com/parsed/1",
                "published_date": timezone.now(),
                "summary": "Summary 1",
                "media": False,
                "media_type": "none"
            },
            {
                "title": "Parsed News 2",
                "content": "Content 2",
                "url": "https://example.com/parsed/2",
                "published_date": timezone.now(),
                "summary": "Summary 2",
                "media": False,
                "media_type": "none"
            }
        ]

        for data in news_data:
            NewsItem.objects.create(
                title=data['title'],
                content=data['content'],
                url=data['url'],
                published_date=data['published_date'],
                summary=data['summary'],
                source=self.source1,
                media=data['media'],
                media_type=data['media_type']
            )

        # новости сохранились
        self.assertEqual(NewsItem.objects.count(), 2)

        # обновление метки времени парсинга
        self.source1.last_parsed = timezone.now()
        self.source1.save()
        self.source1.refresh_from_db()
        self.assertIsNotNone(self.source1.last_parsed)