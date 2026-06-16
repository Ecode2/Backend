from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, OpenApiTypes

from .models import (
    AudioChapter,
    Book,
    BookFile,
    Bookmark,
    ReaderSettings,
    ReadingProgress,
)


class BookFileSerializer(serializers.ModelSerializer):
    file = serializers.FileField()
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

    class Meta:
        model = Book
        fields = [
            "id", "title", "description", "user", "author", "production_year",
            "status", "book_type", "language_code", "cover_url",
            "total_page", "total_segments", "duration_estimate_ms",
            "files", "updated_at", "created_at",
        ]
        read_only_fields = [
            "id", "user", "created_at", "updated_at", "cover_url",
            "total_segments", "duration_estimate_ms",
        ]


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
    book_id = serializers.IntegerField()
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
            "page", "percent", "audio_ms", "updated_at",
        ]
        read_only_fields = ["updated_at"]


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
