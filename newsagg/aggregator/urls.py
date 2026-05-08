from django.urls import path
from . import views

urlpatterns = [
    path("", views.news_list, name="news_list"),
    path("news/<int:pk>/", views.news_detail_card, name="news_detail_card"),
    path("tags/suggest/", views.tag_suggest, name="tag_suggest"),
    path("feed/lenta/", views.news_feed_lenta, name="news_feed_lenta"),
    path("feed/actual/", views.news_feed_actual, name="news_feed_actual"),
]