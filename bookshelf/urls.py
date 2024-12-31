from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"books", views.BookViewSet, basename="books")
router.register(r"files", views.BookFileViewSet, basename="book_files")

urlpatterns = [
    path("", include(router.urls)),
]
