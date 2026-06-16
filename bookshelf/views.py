"""Bookshelf REST API.

Bug fixes vs. the original (Section 2 of the spec):
  * ``BookFileViewSet`` permission attribute name is correct now.
  * No ``cache_page`` on per-user/private content (it ignored the user and
    could serve one user's private page to another).
  * Page endpoints use the cached parse structure instead of re-downloading
    the file on every request and leaking temp files.
  * ``read-page`` returns a JSON error body when ``page`` is missing.
  * Single ``cache_with_prefix`` definition.
"""

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from django.views.decorators.cache import cache_page

from rest_framework import filters, pagination, permissions, response, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter

from . import services
from .filters import BookFileFilter
from .models import Book, BookFile, Bookmark, ReaderSettings, ReadingProgress
from .permissions import IsBookCreator, IsFileAuthor, PublicOrPrivate
from .serializers import (
    AudioChapterSerializer,
    BookFileSerializer,
    BookSerializer,
    BookmarkSerializer,
    ReaderSettingsSerializer,
    ReadingProgressSerializer,
    SegmentSerializer,
    TocResponseSerializer,
    VoiceSerializer,
)


def cache_with_prefix(timeout, prefix):
    """Cache a view response under a known prefix (only for public content)."""
    def decorator(view_func):
        return cache_page(timeout, key_prefix=prefix)(view_func)
    return decorator


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    pagination_class = pagination.LimitOffsetPagination
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    filterset_fields = ["title", "author", "created_at", "updated_at", "status", "book_type"]
    search_fields = ["title", "author", "description", "status"]
    ordering_fields = ["title", "production_year", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        qs = Book.objects.prefetch_related("files")
        if user.is_authenticated:
            return qs.filter(Q(user=user) | Q(status="public"))
        return qs.filter(status="public")

    def get_permissions(self):
        if self.action in ["update", "partial_update", "destroy"]:
            return [IsBookCreator()]
        if self.action in ["read_one_page", "read_all_pages", "toc", "segments", "chapters"]:
            return [PublicOrPrivate()]
        if self.action in ["progress", "bookmarks", "delete_bookmark"]:
            return [permissions.IsAuthenticated(), PublicOrPrivate()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # -- structure-derived endpoints -------------------------------------
    def _structure(self, book):
        book_file = book.primary_file()
        if not book_file or book_file.is_audio:
            return None
        return services.get_or_build_structure(book_file)

    @extend_schema(
        parameters=[OpenApiParameter("page", type=int, description="1-based PDF page")]
    )
    @action(detail=True, methods=["get"], url_path="read-page", url_name="read_page")
    def read_one_page(self, request, pk=None):
        page_number = request.query_params.get("page")
        if not page_number:
            return response.Response(
                {"detail": "The 'page' query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            return response.Response(
                {"detail": "'page' must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        book = self.get_object()
        structure = self._structure(book)
        if structure is None:
            return response.Response(
                {"detail": "No readable document file for this book."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return response.Response({page_number: services.page_text(structure, page_number)})

    @action(detail=True, methods=["get"], url_path="pages", url_name="all_page")
    def read_all_pages(self, request, pk=None, *args, **kwargs):
        book = self.get_object()
        structure = self._structure(book)
        if structure is None:
            return response.Response(
                {"detail": "No readable document file for this book."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return response.Response(services.pages_from_structure(structure))

    @extend_schema(responses=TocResponseSerializer)
    @action(detail=True, methods=["get"], url_path="toc")
    def toc(self, request, pk=None):
        book = self.get_object()
        if book.is_audiobook:
            chapters = book.audio_chapters.all()
            return response.Response({
                "book_id": book.id,
                "book_type": book.book_type,
                "fmt": "audio",
                "total_segments": book.total_segments or chapters.count(),
                "duration_estimate_ms": book.duration_estimate_ms or 0,
                "toc": AudioChapterSerializer(chapters, many=True).data,
            })
        structure = self._structure(book)
        if structure is None:
            return response.Response(
                {"detail": "No readable document file for this book."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return response.Response({
            "book_id": book.id,
            "book_type": book.book_type,
            "fmt": book.primary_file().fmt,
            "total_segments": len(structure.segments),
            "duration_estimate_ms": book.duration_estimate_ms or 0,
            "toc": structure.toc,
        })

    @extend_schema(
        parameters=[
            OpenApiParameter("start", type=int, description="first segment index"),
            OpenApiParameter("count", type=int, description="number of segments"),
        ],
        responses=SegmentSerializer(many=True),
    )
    @action(detail=True, methods=["get"], url_path="segments")
    def segments(self, request, pk=None):
        book = self.get_object()
        structure = self._structure(book)
        if structure is None:
            return response.Response(
                {"detail": "No readable document file for this book."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            start = max(0, int(request.query_params.get("start", 0)))
            count = int(request.query_params.get("count", 100))
        except (TypeError, ValueError):
            return response.Response(
                {"detail": "'start' and 'count' must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        count = max(1, min(count, 500))
        window = structure.segments[start:start + count]
        return response.Response({
            "start": start,
            "count": len(window),
            "total": len(structure.segments),
            "segments": window,
        })

    @action(detail=True, methods=["get"], url_path="chapters")
    def chapters(self, request, pk=None):
        book = self.get_object()
        return response.Response(
            AudioChapterSerializer(book.audio_chapters.all(), many=True).data
        )

    # -- progress --------------------------------------------------------
    @extend_schema(request=ReadingProgressSerializer, responses=ReadingProgressSerializer)
    @action(detail=True, methods=["get", "put"], url_path="progress")
    def progress(self, request, pk=None):
        book = self.get_object()
        obj, _ = ReadingProgress.objects.get_or_create(user=request.user, book=book)
        if request.method == "GET":
            return response.Response(ReadingProgressSerializer(obj).data)
        serializer = ReadingProgressSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, book=book)
        return response.Response(serializer.data)

    # -- bookmarks -------------------------------------------------------
    @extend_schema(request=BookmarkSerializer, responses=BookmarkSerializer(many=True))
    @action(detail=True, methods=["get", "post"], url_path="bookmarks")
    def bookmarks(self, request, pk=None):
        book = self.get_object()
        if request.method == "GET":
            qs = Bookmark.objects.filter(user=request.user, book=book)
            return response.Response(BookmarkSerializer(qs, many=True).data)
        serializer = BookmarkSerializer(data={**request.data, "book": book.id})
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, book=book)
        return response.Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"bookmarks/(?P<bookmark_id>\d+)")
    def delete_bookmark(self, request, pk=None, bookmark_id=None):
        book = self.get_object()
        deleted, _ = Bookmark.objects.filter(
            user=request.user, book=book, id=bookmark_id
        ).delete()
        if not deleted:
            return response.Response(status=status.HTTP_404_NOT_FOUND)
        return response.Response(status=status.HTTP_204_NO_CONTENT)


class BookFileViewSet(viewsets.ModelViewSet):
    queryset = BookFile.objects.all()
    serializer_class = BookFileSerializer
    pagination_class = pagination.LimitOffsetPagination
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = BookFileFilter
    ordering_fields = ["book__title", "file", "book__status", "book__created_at"]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            return BookFile.objects.filter(Q(book__user=user) | Q(book__status="public"))
        return BookFile.objects.filter(book__status="public")

    def get_permissions(self):
        if self.action in ["update", "partial_update", "destroy"]:
            return [IsFileAuthor()]
        return super().get_permissions()

    def perform_create(self, serializer):
        book_file = serializer.save()
        # Parse/probe + cover. Synchronous: uploads are infrequent.
        services.process_uploaded_file(book_file)


class ReaderSettingsView(RetrieveUpdateAPIView):
    """Global per-user reader defaults (GET/PUT /api/reader-settings/)."""

    serializer_class = ReaderSettingsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        obj, _ = ReaderSettings.objects.get_or_create(user=self.request.user)
        return obj


class VoicesView(APIView):
    """List available TTS voices (proxied + cached). GET /api/voices/?language="""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "tts"

    @extend_schema(
        parameters=[OpenApiParameter("language", type=str)],
        responses=VoiceSerializer(many=True),
    )
    def get(self, request):
        from django.core.cache import cache
        from .tts import get_tts_service

        language = request.query_params.get("language", "")
        cache_key = f"tts_voices:{language or 'all'}"
        cached = cache.get(cache_key)
        if cached is not None:
            return response.Response(cached)
        try:
            voices = get_tts_service().list_voices(language or None)
        except Exception as exc:  # pragma: no cover - provider/credentials issues
            return response.Response(
                {"detail": f"Voice listing unavailable: {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        cache.set(cache_key, voices, 60 * 30)
        return response.Response(voices)
