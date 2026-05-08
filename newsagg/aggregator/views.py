from types import SimpleNamespace

from django.db.models import Count
from django.shortcuts import render, get_object_or_404

from .models import NewsItem, NewsSource, Tag


POPULAR_TAGS_LIMIT = 20
SUGGESTION_LIMIT = 10


def _parse_tags_param(raw_value: str) -> list[str]:
    if not raw_value:
        return []
    return [
        tag.strip().lower()
        for tag in raw_value.split(",")
        if tag.strip()
    ]


def _build_filter_tags(selected_tags: list[str]):
    """
    Возвращает:
    - выбранные теги (даже если они не входят в топ)
    - затем популярные теги, ограниченные лимитом
    """
    selected_set = set(selected_tags)

    selected_tag_objects = list(
        Tag.objects.filter(name__in=selected_tags)
    )
    selected_by_name = {tag.name.lower(): tag for tag in selected_tag_objects}

    popular_tags = list(
        Tag.objects
        .annotate(news_count=Count("news_items"))
        .filter(news_count__gt=0)
        .order_by("-news_count", "name")[:POPULAR_TAGS_LIMIT]
    )

    result = []

    # Сначала выбранные
    for tag_name in selected_tags:
        result.append(
            selected_by_name.get(
                tag_name,
                SimpleNamespace(name=tag_name, news_count=0)
            )
        )

    # Потом популярные, которых ещё нет среди выбранных
    for tag in popular_tags:
        if tag.name.lower() not in selected_set:
            result.append(tag)

    return result, selected_tag_objects


def news_list(request):
    source_filter = request.GET.get("source", "all")
    selected_tags = _parse_tags_param(request.GET.get("tags", ""))

    sources = (
        NewsSource.objects
        .filter(is_active=True)
        .order_by("name")
    )

    actual_news = (
        NewsItem.objects
        .select_related("source")
        .prefetch_related("tags")
        .order_by("-published_date")[:10]
    )

    lenta_news = (
        NewsItem.objects
        .select_related("source")
        .prefetch_related("tags")
        .order_by("-published_date")
    )

    if source_filter != "all":
        lenta_news = lenta_news.filter(source_id=source_filter)

    for tag_name in selected_tags:
        lenta_news = lenta_news.filter(tags__name__iexact=tag_name)

    lenta_news = lenta_news.distinct()

    filter_tags, selected_tag_objects = _build_filter_tags(selected_tags)

    context = {
        "sources": sources,
        "actual_news": actual_news,
        "lenta_news": lenta_news[:50],
        "tags": filter_tags,
        "selected_tags": selected_tags,
        "selected_tag_objects": selected_tag_objects,
        "active_filter": source_filter if source_filter != "all" else "all",
    }

    if request.headers.get("HX-Request"):
        return render(request, "aggregator/news_lenta_panel.html", context)

    return render(request, "aggregator/news_list.html", context)


def tag_suggest(request):
    q = request.GET.get("q", "").strip().lower()
    selected_tags = _parse_tags_param(request.GET.get("selected", ""))

    qs = (
        Tag.objects
        .annotate(news_count=Count("news_items"))
        .filter(news_count__gt=0)
        .order_by("-news_count", "name")
    )

    if q:
        qs = qs.filter(name__icontains=q)

    if selected_tags:
        qs = qs.exclude(name__in=selected_tags)

    tags = qs[:SUGGESTION_LIMIT]

    return render(
        request,
        "aggregator/tag_suggestions.html",
        {
            "tags": tags,
            "query": q,
        }
    )


def news_detail_card(request, pk):
    item = (
        NewsItem.objects
        .select_related("source")
        .prefetch_related("tags", "media_files")
        .get(pk=pk)
    )
    return render(request, "aggregator/news_card.html", {"item": item})

def news_feed_lenta(request):
    source_filter = request.GET.get("source", "all")
    selected_tags = [t.strip().lower() for t in request.GET.get("tags", "").split(",") if t.strip()]

    qs = NewsItem.objects.select_related("source").prefetch_related("tags").order_by("-published_date")

    if source_filter != "all":
        qs = qs.filter(source_id=source_filter)

    for tag_name in selected_tags:
        qs = qs.filter(tags__name__iexact=tag_name)

    qs = qs.distinct()[:50]

    return render(request, "aggregator/news_feed_lenta.html", {
        "lenta_news": qs
    })

def news_feed_actual(request):
    actual_news = (
        NewsItem.objects
        .select_related("source")
        .prefetch_related("tags")
        .order_by("-published_date")[:10]
    )

    return render(
        request,
        "aggregator/news_feed_actual.html",
        {
            "actual_news": actual_news
        }
    )