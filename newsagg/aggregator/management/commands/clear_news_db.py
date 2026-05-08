from django.core.management.base import BaseCommand
from django.db import connection, transaction

from aggregator.models import (
    NewsSource,
    NewsItem,
    MediaFile,
    Tag,
    NewsItemTag,
)


class Command(BaseCommand):
    help = "Полная очистка новостной БД"

    @transaction.atomic
    def handle(self, *args, **options):

        self.stdout.write(
            self.style.WARNING("Начинаю очистку БД...")
        )

        # Удаление данных
        deleted_news_tags = NewsItemTag.objects.all().delete()
        deleted_media = MediaFile.objects.all().delete()
        deleted_news = NewsItem.objects.all().delete()
        deleted_tags = Tag.objects.all().delete()
        deleted_sources = NewsSource.objects.all().delete()

        # Сброс AUTO INCREMENT / SEQUENCE
        self.reset_sequences()

        self.stdout.write(
            self.style.SUCCESS(
                "Очистка завершена успешно.\n"
                f"NewsItemTag: {deleted_news_tags}\n"
                f"MediaFile: {deleted_media}\n"
                f"NewsItem: {deleted_news}\n"
                f"Tag: {deleted_tags}\n"
                f"NewsSource: {deleted_sources}"
            )
        )

    def reset_sequences(self):
        """
        Сброс автоинкрементных ID.
        Поддержка SQLite и PostgreSQL.
        """

        tables = [
            NewsItemTag._meta.db_table,
            MediaFile._meta.db_table,
            NewsItem._meta.db_table,
            Tag._meta.db_table,
            NewsSource._meta.db_table,
        ]

        with connection.cursor() as cursor:

            # SQLite
            if connection.vendor == "sqlite":
                for table in tables:
                    cursor.execute(
                        "DELETE FROM sqlite_sequence WHERE name=%s",
                        [table]
                    )

            # PostgreSQL
            elif connection.vendor == "postgresql":
                for table in tables:
                    cursor.execute(
                        f'ALTER SEQUENCE "{table}_id_seq" RESTART WITH 1'
                    )