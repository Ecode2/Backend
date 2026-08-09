from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"books", views.BookViewSet, basename="books")
router.register(r"files", views.BookFileViewSet, basename="book_files")

urlpatterns = [
    path("api/reader-settings/", views.ReaderSettingsView.as_view(), name="reader_settings"),
    path("api/voices/", views.VoicesView.as_view(), name="voices"),
    path("api/stats/", views.LibraryStatsView.as_view(), name="library_stats"),
    path("", include(router.urls)),
]
