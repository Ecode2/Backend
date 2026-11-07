from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, OpenApiTypes

from .models import (
    AudioChapter,
    Book,
    BookFile,
    Bookmark,
    ReaderSettings,
    ReadingProgress,
    file_validation,
)


class BookFileSerializer(serializers.ModelSerializer):
    # Declaring the field explicitly replaces the one ModelSerializer would
    # build from the model, which also drops the model field's validators.
    # Without this, the API accepted *any* file type or size (the format and
    # 50MB/500MB limits were silently unenforced) and only failed later during
    # parsing, where the exception is swallowed.
    file = serializers.FileField(validators=[file_validation])
    url = serializers.SerializerMethodField()

    class Meta:
        model = BookFile
        fields = [
            "id", "book", "file", "url", "fmt", "size_bytes", "checksum",
            "order", "track_title", "duration_ms",
        ]
        read_only_fields = ["id", "fmt", "size_bytes", "checksum", "duration_ms", "url"]

    @extend_schema_field(OpenApiTypes.URI)
    def get_url(self, obj):
        try:
            return obj.file.url
        except Exception:
            return None


class BookSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    files = BookFileSerializer(many=True, read_only=True)
    # Signed per request: S3/MinIO URLs expire, so a stored one goes stale.
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            "id", "title", "description", "user", "author", "production_year",
            "status", "book_type", "language_code", "cover_url",
            "total_page", "total_segments", "duration_estimate_ms",
            "files", "updated_at", "created_at",
        ]
        # NB: "cover_url" is declared above; DRF rejects listing a declared
        # field here as well. SerializerMethodField is already read-only.
        read_only_fields = [
            "id", "user", "created_at", "updated_at",
            "total_segments", "duration_estimate_ms",
        ]

    @extend_schema_field(OpenApiTypes.URI)
    def get_cover_url(self, obj):
        """Fresh URL for the stored cover key, falling back to legacy rows."""
        if obj.cover_path:
            try:
                from django.core.files.storage import default_storage

                return default_storage.url(obj.cover_path)
            except Exception:
                pass
        return obj.cover_url or None


class TocEntrySerializer(serializers.Serializer):
    index = serializers.IntegerField()
    title = serializers.CharField()
    level = serializers.IntegerField()
    start_segment = serializers.IntegerField()
    page = serializers.IntegerField(allow_null=True)


class SegmentSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    kind = serializers.CharField()
    level = serializers.IntegerField(allow_null=True)
    text = serializers.CharField()
    chapter_index = serializers.IntegerField()
    page = serializers.IntegerField(allow_null=True)
    char_count = serializers.IntegerField()


class TocResponseSerializer(serializers.Serializer):
    book_id = serializers.UUIDField()
    book_type = serializers.CharField()
    fmt = serializers.CharField()
    total_segments = serializers.IntegerField()
    duration_estimate_ms = serializers.IntegerField()
    toc = TocEntrySerializer(many=True)


class AudioChapterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudioChapter
        fields = ["index", "title", "start_ms", "end_ms", "book_file"]


class ReadingProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingProgress
        fields = [
            "book", "segment_index", "char_offset", "chapter_index",
            "page", "percent", "locator", "audio_ms", "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def update(self, instance, validated_data):
        # A bare segment_index write (the text reader / narration) makes any
        # stored page locator stale, so drop it; the locator wins only when the
        # same request supplies it.
        if "segment_index" in validated_data and "locator" not in validated_data:
            validated_data["locator"] = {}
        if (
            "percent" not in validated_data
            and "segment_index" in validated_data
            and instance.book.book_type == "document"
        ):
            total = max(1, instance.book.total_segments or 1)
            validated_data["percent"] = round(
                min(1.0, validated_data["segment_index"] / total) * 100, 2
            )
        return super().update(instance, validated_data)

    def validate_percent(self, value):
        return max(0.0, min(100.0, value))

    def validate_locator(self, value):
        # Opaque to the server, but bounded: this is client-supplied JSON.
        if not isinstance(value, dict):
            raise serializers.ValidationError("locator must be an object.")
        if len(str(value)) > 2000:
            raise serializers.ValidationError("locator is too large.")
        return value


class BookmarkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bookmark
        fields = [
            "id", "book", "segment_index", "audio_ms", "label",
            "note", "color", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ReaderSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReaderSettings
        exclude = ["id", "user"]


class VoiceSerializer(serializers.Serializer):
    name = serializers.CharField()
    language_codes = serializers.ListField(child=serializers.CharField())
    ssml_gender = serializers.CharField()
    natural_sample_rate_hertz = serializers.IntegerField(required=False)
    # NVIDIA encodes these in the voice id; surfaced so the UI can group by
    # speaker and offer emotion variants instead of one flat list.
    speaker = serializers.CharField(required=False, allow_blank=True)
    emotion = serializers.CharField(required=False, allow_blank=True)
    model = serializers.CharField(required=False, allow_blank=True)


# A single heartbeat covers seconds, not minutes. Clamping the accepted delta
# stops a stuck retry loop -- or a hostile client -- from inflating the totals.
MAX_LISTENING_REPORT_MS = 5 * 60 * 1000


class ListeningReportSerializer(serializers.Serializer):
    """One slice of measured wall-clock listening time."""

    ms = serializers.IntegerField(min_value=1, max_value=MAX_LISTENING_REPORT_MS)


class LibraryStatsSerializer(serializers.Serializer):
    """Aggregate reading stats for the authenticated user.

    ``listening_ms`` and friends are *measured*: the player reports the
    wall-clock time it actually spent playing, which the server accumulates.
    ``estimated_listening_ms`` remains as a rough fallback for books listened
    to before measurement existed.
    """

    books_in_library = serializers.IntegerField()
    documents = serializers.IntegerField()
    audiobooks = serializers.IntegerField()
    books_started = serializers.IntegerField()
    books_completed = serializers.IntegerField()
    books_in_progress = serializers.IntegerField()
    bookmarks = serializers.IntegerField()

    # Measured listening time.
    listening_ms = serializers.IntegerField()
    listening_today_ms = serializers.IntegerField()
    listening_daily_average_ms = serializers.IntegerField()
    days_listened = serializers.IntegerField()
    current_streak_days = serializers.IntegerField()

    # Retained estimate (narration duration x progress) for context.
    estimated_listening_ms = serializers.IntegerField()
