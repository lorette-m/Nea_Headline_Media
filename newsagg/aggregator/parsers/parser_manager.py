import time
import logging

from django.utils import timezone

from aggregator.models import NewsSource
from aggregator.parsers.rss_parser import RSSParser
from llm_processing.llm_service import process_news

logger = logging.getLogger(__name__)


class ParserManager:
    """Менеджер RSS-парсеров + LLM обработки."""

    def __init__(self):
        self.parsers = {
            "rss": RSSParser,
        }

    def get_parser(self, source: NewsSource):
        parser_class = self.parsers.get(source.source_type)

        if parser_class:
            return parser_class(source)

        return None

    def parse_all_sources(self) -> int:
        """
        Полный pipeline:
        RSS -> save_news_item -> LLM processing
        """

        start_time = time.time()

        try:
            active_sources = NewsSource.objects.filter(is_active=True)

            logger.info(
                "Запуск парсинга %s RSS источников",
                active_sources.count()
            )

            total_saved = 0
            total_processed = 0
            total_failed = 0

            for source in active_sources:

                parser = self.get_parser(source)

                if not parser:
                    logger.warning(
                        "Не найден parser для source_type=%s",
                        source.source_type
                    )
                    continue

                try:
                    logger.info("Парсим источник: %s", source.name)

                    news_items = parser.parse()

                    source_saved = 0
                    source_processed = 0
                    source_failed = 0

                    for news_data in news_items:

                        try:
                            news_item = parser.save_news_item(news_data)

                            # новость уже существует
                            if not news_item:
                                continue

                            source_saved += 1

                            # LLM processing
                            success = process_news(news_item)

                            if success:
                                source_processed += 1
                            else:
                                source_failed += 1

                        except Exception as e:
                            source_failed += 1

                            logger.exception(
                                "Ошибка обработки новости "
                                "из источника %s: %s",
                                source.name,
                                e
                            )

                    source.last_parsed = timezone.now()
                    source.save(update_fields=["last_parsed"])

                    logger.info(
                        "%s -> сохранено: %s | "
                        "обработано: %s | "
                        "ошибок: %s",
                        source.name,
                        source_saved,
                        source_processed,
                        source_failed
                    )

                    total_saved += source_saved
                    total_processed += source_processed
                    total_failed += source_failed

                except Exception as e:
                    logger.exception(
                        "Ошибка парсинга источника %s: %s",
                        source.name,
                        e
                    )

            duration = time.time() - start_time

            logger.info(
                "Pipeline завершен | "
                "сохранено=%s | "
                "обработано=%s | "
                "ошибок=%s | "
                "время=%.1f сек",
                total_saved,
                total_processed,
                total_failed,
                duration
            )

            return total_processed

        except Exception as e:
            logger.exception(
                "Критическая ошибка parse_all_sources: %s",
                e
            )
            return 0