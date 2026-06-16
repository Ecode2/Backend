"""Bookverse data model.

Position is anchored on the *segment index* (see ``bookshelf.parsing``), which
unifies resume, bookmarks and progress across PDF/EPUB/DOCX/TXT documents and
native audiobooks. Files (documents and audio) live in S3-compatible storage.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import models

from .files import detect_format, is_audio_format, is_document_format

PUBLIC = "public"
PRIVATE = "private"
BOOK_STATUS = [(PUBLIC, "Public"), (PRIVATE, "Private")]

DOCUMENT = "document"
AUDIOBOOK = "audiobook"
BOOK_TYPES = [(DOCUMENT, "Document"), (AUDIOBOOK, "Audiobook")]

FORMAT_CHOICES = [
    ("pdf", "PDF"), ("epub", "EPUB"), ("docx", "DOCX"), ("txt", "TXT"),
    ("mp3", "MP3"), ("m4a", "M4A"), ("m4b", "M4B"), ("aac", "AAC"),
    ("ogg", "OGG"), ("opus", "OPUS"), ("wav", "WAV"), ("flac", "FLAC"),
]

# Documents are capped tighter than audiobooks (whole audiobooks are large).
DOCUMENT_MAX_BYTES = 1024 * 1024 * 50      # 50 MB
AUDIO_MAX_BYTES = 1024 * 1024 * 500        # 500 MB


class Book(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="books", on_delete=models.CASCADE
    )
    author = models.CharField(max_length=255, blank=True, null=True)
    production_year = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=BOOK_STATUS, default=PRIVATE)

    book_type = models.CharField(max_length=20, choices=BOOK_TYPES, default=DOCUMENT)
    language_code = models.CharField(max_length=16, default="en-US")
    cover_url = models.URLField(blank=True, null=True)

    # Denormalized after parsing / audio probing, for fast library rendering.
    total_page = models.IntegerField(null=True, blank=True, default=0)
    total_segments = models.IntegerField(null=True, blank=True, default=0)
    duration_estimate_ms = models.BigIntegerField(null=True, blank=True, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_audiobook(self) -> bool:
        return self.book_type == AUDIOBOOK

    def primary_file(self):
        return self.files.order_by("order", "id").first()


def handle_file_upload(instance, filename):
    return f"books/{instance.book.id}/{filename}"


def file_validation(file):
    if not file:
        raise ValidationError("No file selected.")
    if not isinstance(file, UploadedFile):
        return
    fmt = detect_format(file.name)
    if is_audio_format(fmt):
        if file.size > AUDIO_MAX_BYTES:
            raise ValidationError("Audio file shouldn't be larger than 500MB.")
    elif is_document_format(fmt):
        if file.size > DOCUMENT_MAX_BYTES:
            raise ValidationError("Document shouldn't be larger than 50MB.")
    else:
        raise ValidationError(
            f"Unsupported file type: .{fmt}. Allowed: pdf, epub, docx, txt, "
            "mp3, m4a, m4b, aac, ogg, opus, wav, flac."
        )


class BookFile(models.Model):
    book = models.ForeignKey(Book, related_name="files", on_delete=models.CASCADE)
    file = models.FileField(upload_to=handle_file_upload, validators=[file_validation])

    fmt = models.CharField(max_length=8, choices=FORMAT_CHOICES, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    checksum = models.CharField(max_length=64, blank=True, db_index=True)

    # Native-audiobook playlist support (BookPlayer style multi-file books).
    order = models.PositiveIntegerField(default=0)
    track_title = models.CharField(max_length=255, blank=True)
    duration_ms = models.BigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.book.title} - {self.file.name}"

    @property
    def is_audio(self) -> bool:
        return is_audio_format(self.fmt)

    def save(self, *args, **kwargs):
        # Auto-detect format and capture size/checksum on first save.
        if self.file and not self.fmt:
            self.fmt = detect_format(self.file.name)
        if self.file and self.size_bytes is None:
            try:
                self.size_bytes = self.file.size
            except (ValueError, OSError):
                self.size_bytes = None
        if self.file and not self.checksum:
            from .files import compute_checksum
            try:
                self.checksum = compute_checksum(self.file)
            except Exception:
                self.checksum = ""
        super().save(*args, **kwargs)


class DocumentStructure(models.Model):
    """Cached parse result for a document BookFile (parse once, reuse)."""

    book_file = models.OneToOneField(
        BookFile, related_name="structure", on_delete=models.CASCADE
    )
    segments = models.JSONField(default=list)
    toc = models.JSONField(default=list)
    parser_version = models.IntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Structure<{self.book_file_id}> ({len(self.segments)} segments)"


class ReadingProgress(models.Model):
    """Per-user resume anchor for a book (backend-managed, cross-device)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="reading_progress",
        on_delete=models.CASCADE,
    )
    book = models.ForeignKey(
        Book, related_name="progress", on_delete=models.CASCADE
    )
    segment_index = models.IntegerField(default=0)
    char_offset = models.IntegerField(default=0)
    chapter_index = models.IntegerField(default=0)
    page = models.IntegerField(null=True, blank=True)
    percent = models.FloatField(default=0.0)
    # For native audiobooks: position within the currently playing track.
    audio_ms = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "book")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user} @ {self.book} seg={self.segment_index}"


class Bookmark(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="bookmarks", on_delete=models.CASCADE
    )
    book = models.ForeignKey(
        Book, related_name="bookmarks", on_delete=models.CASCADE
    )
    segment_index = models.IntegerField(default=0)
    audio_ms = models.BigIntegerField(null=True, blank=True)
    label = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    color = models.CharField(max_length=9, blank=True)  # #RRGGBB(AA)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["segment_index", "created_at"]

    def __str__(self):
        return f"Bookmark<{self.book_id}> seg={self.segment_index}"


THEME_CHOICES = [("light", "Light"), ("sepia", "Sepia"), ("dark", "Dark"), ("night", "Night")]


class ReaderSettings(models.Model):
    """Global per-user reader defaults."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="reader_settings",
        on_delete=models.CASCADE,
    )
    voice_name = models.CharField(max_length=64, default="en-US-Neural2-F")
    language_code = models.CharField(max_length=16, default="en-US")
    speaking_rate = models.FloatField(default=1.0)  # baked TTS rate; keep 1.0
    pitch = models.FloatField(default=0.0)
    speed = models.FloatField(default=1.0)          # client playbackRate
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default="light")
    font_family = models.CharField(max_length=64, default="Georgia")
    font_size = models.IntegerField(default=18)
    auto_scroll = models.BooleanField(default=True)
    skip_back_seconds = models.IntegerField(default=15)
    skip_forward_seconds = models.IntegerField(default=30)

    def __str__(self):
        return f"ReaderSettings<{self.user_id}>"


class AudioSegmentCache(models.Model):
    """Deduped synthesized audio, keyed by sha256(text|voice|encoding)."""

    cache_key = models.CharField(max_length=64, unique=True, db_index=True)
    storage_url = models.URLField(max_length=1024)
    storage_path = models.CharField(max_length=1024, blank=True)
    duration_ms = models.IntegerField(default=0)
    byte_size = models.BigIntegerField(default=0)
    voice = models.CharField(max_length=64, blank=True)
    encoding = models.CharField(max_length=16, default="MP3")
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"AudioCache<{self.cache_key[:12]}>"


class AudioChapter(models.Model):
    """Chapter marker for a native audiobook (from m4b/ID3 or file boundary)."""

    book = models.ForeignKey(
        Book, related_name="audio_chapters", on_delete=models.CASCADE
    )
    book_file = models.ForeignKey(
        BookFile, related_name="chapters", on_delete=models.CASCADE,
        null=True, blank=True,
    )
    index = models.IntegerField(default=0)
    title = models.CharField(max_length=255)
    start_ms = models.BigIntegerField(default=0)   # offset within book_file
    end_ms = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["index"]

    def __str__(self):
        return f"AudioChapter<{self.book_id}> {self.index}: {self.title}"
