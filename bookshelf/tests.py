"""Tests for the parsing layer (one fixture per format) and the WS protocol."""

import os
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase, override_settings

from bookshelf.parsing import parse_document
from bookshelf.parsing.normalize import normalize_text, split_sentences


class NormalizeTests(TestCase):
    def test_hyphenated_linebreak_joined(self):
        self.assertEqual(normalize_text("exam-\nple"), "example")

    def test_whitespace_collapsed(self):
        self.assertEqual(normalize_text("a   b\t c\n\n d"), "a b c d")

    def test_smart_quotes_normalized(self):
        self.assertEqual(normalize_text("“hi”"), '"hi"')

    def test_sentence_split(self):
        self.assertEqual(
            split_sentences("One. Two! Three?"), ["One.", "Two!", "Three?"]
        )


class TxtParserTests(TestCase):
    def _parse(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(text)
            path = f.name
        try:
            return parse_document(path, "txt")
        finally:
            os.remove(path)

    def test_chapters_detected(self):
        segments, toc = self._parse(
            "Chapter 1\n\nHello world.\n\nChapter 2\n\nMore text here."
        )
        titles = [t.title for t in toc]
        self.assertIn("Chapter 1", titles)
        self.assertIn("Chapter 2", titles)
        self.assertTrue(all(s.index == i for i, s in enumerate(segments)))

    def test_single_chapter_fallback(self):
        segments, toc = self._parse("Just a paragraph.\n\nAnd another.")
        self.assertEqual(len(toc), 1)
        self.assertEqual(len(segments), 2)


class DocxParserTests(TestCase):
    def test_headings_and_paragraphs(self):
        import docx

        document = docx.Document()
        document.add_heading("Introduction", level=1)
        document.add_paragraph("First paragraph.")
        document.add_heading("Methods", level=1)
        document.add_paragraph("Second paragraph.")
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            path = f.name
        document.save(path)
        try:
            segments, toc = parse_document(path, "docx")
        finally:
            os.remove(path)
        self.assertEqual([t.title for t in toc], ["Introduction", "Methods"])
        self.assertTrue(any(s.kind == "heading" for s in segments))


class PdfParserTests(TestCase):
    def test_extracts_text_and_pages(self):
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello PDF world.", fontsize=12)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        doc.save(path)
        doc.close()
        try:
            segments, toc = parse_document(path, "pdf")
        finally:
            os.remove(path)
        self.assertTrue(segments)
        self.assertEqual(segments[0].page, 1)
        self.assertIn("Hello", segments[0].text)


class EpubParserTests(TestCase):
    def test_spine_and_toc(self):
        from ebooklib import epub

        book = epub.EpubBook()
        book.set_identifier("id123")
        book.set_title("Test Book")
        c1 = epub.EpubHtml(title="Chapter One", file_name="c1.xhtml")
        c1.content = "<html><body><h1>Chapter One</h1><p>Body text one.</p></body></html>"
        book.add_item(c1)
        book.toc = (epub.Link("c1.xhtml", "Chapter One", "c1"),)
        book.spine = [c1]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as f:
            path = f.name
        epub.write_epub(path, book)
        try:
            segments, toc = parse_document(path, "epub")
        finally:
            os.remove(path)
        self.assertTrue(any("Body text one." in s.text for s in segments))
        self.assertTrue(toc)


@override_settings(TTS_PROVIDER="dummy")
class ReaderConsumerTests(TransactionTestCase):
    # TransactionTestCase, not TestCase: the consumer touches the database from
    # a separate thread via database_sync_to_async, which cannot see (or safely
    # share) the transaction TestCase opens on the main thread. Against SQLite
    # that happened to work; against Postgres it fails with
    # "psycopg2.InterfaceError: connection already closed".
    async def test_ready_and_play_protocol(self):
        from channels.testing import WebsocketCommunicator
        from channels.db import database_sync_to_async
        from system.asgi import application
        from bookshelf.models import Book, BookFile
        from bookshelf.services import get_or_build_structure
        from bookshelf.ws_auth import make_ws_ticket

        @database_sync_to_async
        def setup():
            user = User.objects.create_user("reader", password="pw12345!")
            book = Book.objects.create(title="T", user=user, status="public")
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write("Hello one. Hello two.\n\nSecond paragraph here.")
                path = f.name
            from django.core.files import File as DjangoFile
            with open(path, "rb") as fh:
                bf = BookFile(book=book)
                bf.file.save("t.txt", DjangoFile(fh), save=True)
            os.remove(path)
            get_or_build_structure(bf)
            return user, book

        user, book = await setup()
        ticket = await database_sync_to_async(make_ws_ticket)(user)
        communicator = WebsocketCommunicator(
            application, f"/ws/reader/{book.id}/?ticket={ticket}"
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        ready = await communicator.receive_json_from()
        self.assertEqual(ready["type"], "ready")
        self.assertEqual(ready["book_type"], "document")
        self.assertGreaterEqual(ready["total_segments"], 1)

        await communicator.send_json_to({"action": "play", "segment_index": 0})
        meta = await communicator.receive_json_from()
        self.assertEqual(meta["type"], "segment_meta")
        audio = await communicator.receive_from()
        self.assertIsInstance(audio, bytes)
        self.assertTrue(len(audio) > 0)

        await communicator.disconnect()


class LibraryStatsTests(TestCase):
    """GET /api/stats/ must aggregate real stored data, not placeholders."""

    def setUp(self):
        from bookshelf.models import Book, Bookmark, ReadingProgress

        self.user = User.objects.create_user("statsuser", password="pw12345!")
        other = User.objects.create_user("other", password="pw12345!")

        self.doc = Book.objects.create(
            title="Doc", user=self.user, book_type="document",
            duration_estimate_ms=60_000,
        )
        self.audio = Book.objects.create(
            title="Audio", user=self.user, book_type="audiobook",
            duration_estimate_ms=100_000,
        )
        # A public book owned by someone else that this user has started.
        foreign = Book.objects.create(
            title="Foreign", user=other, status="public",
            duration_estimate_ms=200_000,
        )

        ReadingProgress.objects.create(user=self.user, book=self.doc, percent=100.0)
        ReadingProgress.objects.create(user=self.user, book=self.audio, percent=50.0)
        ReadingProgress.objects.create(user=self.user, book=foreign, percent=0.0)
        Bookmark.objects.create(user=self.user, book=self.doc, segment_index=3)

    def _get(self):
        # Only JWTAuthentication is configured, so Django's session-based
        # force_login() would not authenticate the request.
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.user)
        return client.get("/api/stats/")

    def test_requires_authentication(self):
        from rest_framework.test import APIClient

        self.assertIn(APIClient().get("/api/stats/").status_code, (401, 403))

    def test_counts_only_own_books_in_library(self):
        data = self._get().json()
        # "Foreign" is readable but not owned, so it must not inflate the library.
        self.assertEqual(data["books_in_library"], 2)
        self.assertEqual(data["documents"], 1)
        self.assertEqual(data["audiobooks"], 1)

    def test_progress_buckets(self):
        data = self._get().json()
        # percent=0 counts as not started, 100 as completed, 50 as in progress.
        self.assertEqual(data["books_started"], 2)
        self.assertEqual(data["books_completed"], 1)
        self.assertEqual(data["books_in_progress"], 1)

    def test_estimated_listening_time_weights_duration_by_progress(self):
        data = self._get().json()
        # 60000*1.0 + 100000*0.5 + 200000*0.0 = 110000
        self.assertEqual(data["estimated_listening_ms"], 110_000)

    def test_bookmarks_counted(self):
        self.assertEqual(self._get().json()["bookmarks"], 1)


class BookFileManagementTests(TestCase):
    """The endpoints the frontend's edit dialog relies on.

    Covers the two things the UI newly exposes: uploading a non-PDF document
    (EPUB) and replacing a file that was uploaded by mistake.
    """

    def setUp(self):
        from rest_framework.test import APIClient
        from bookshelf.models import Book

        self.user = User.objects.create_user("owner", password="pw12345!")
        self.stranger = User.objects.create_user("stranger", password="pw12345!")
        self.book = Book.objects.create(title="B", user=self.user)

        self.client_ = APIClient()
        self.client_.force_authenticate(user=self.user)

    def _epub_bytes(self):
        from ebooklib import epub

        book = epub.EpubBook()
        book.set_identifier("id1")
        book.set_title("T")
        c1 = epub.EpubHtml(title="One", file_name="c1.xhtml")
        c1.content = "<html><body><h1>One</h1><p>Epub body text.</p></body></html>"
        book.add_item(c1)
        book.toc = (epub.Link("c1.xhtml", "One", "c1"),)
        book.spine = [c1]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as f:
            path = f.name
        epub.write_epub(path, book)
        try:
            with open(path, "rb") as fh:
                return fh.read()
        finally:
            os.remove(path)

    def _upload(self, name, content, client=None):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile(name, content)
        return (client or self.client_).post(
            "/files/",
            {"book": self.book.id, "file": upload, "order": 0},
            format="multipart",
        )

    def test_epub_upload_is_accepted_and_parsed(self):
        res = self._upload("story.epub", self._epub_bytes())
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["fmt"], "epub")

    def test_unsupported_extension_rejected(self):
        res = self._upload("virus.exe", b"MZ\x00\x00")
        self.assertEqual(res.status_code, 400)

    def test_list_files_filtered_by_book(self):
        self._upload("story.epub", self._epub_bytes())
        res = self.client_.get(f"/files/?book={self.book.id}")
        self.assertEqual(res.status_code, 200)
        rows = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["book"], self.book.id)

    def test_delete_then_reupload_replaces_the_file(self):
        """The 'I picked the wrong file' flow the edit dialog implements."""
        first = self._upload("wrong.txt", b"the wrong book entirely")
        self.assertEqual(first.status_code, 201, first.data)
        file_id = first.data["id"]

        deleted = self.client_.delete(f"/files/{file_id}/")
        self.assertEqual(deleted.status_code, 204)

        second = self._upload("right.epub", self._epub_bytes())
        self.assertEqual(second.status_code, 201, second.data)

        rows = self.client_.get(f"/files/?book={self.book.id}").data
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertEqual([r["fmt"] for r in rows], ["epub"])

    def test_stranger_cannot_delete_someone_elses_file(self):
        from rest_framework.test import APIClient

        file_id = self._upload("story.epub", self._epub_bytes()).data["id"]
        other = APIClient()
        other.force_authenticate(user=self.stranger)
        self.assertIn(other.delete(f"/files/{file_id}/").status_code, (403, 404))

    def test_owner_can_patch_book_details(self):
        res = self.client_.patch(
            f"/books/{self.book.id}/",
            {"title": "New", "author": "A", "production_year": 2021, "status": "public"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["title"], "New")
        self.assertEqual(res.data["status"], "public")


class ChannelLayerConfigTests(TestCase):
    """Guards the Redis socket-timeout invariant the audio WebSocket depends on.

    channels_redis waits for messages with a blocking BZPOPMIN that lasts
    ``brpop_timeout`` seconds. redis-py >= 6 defaults ``socket_timeout`` to 5s,
    which is exactly that long, so an idle WebSocket died with
    "redis.exceptions.TimeoutError: Timeout reading from ...".
    """

    def test_socket_timeout_exceeds_blocking_pop_timeout(self):
        from django.conf import settings
        from channels_redis.core import RedisChannelLayer

        hosts = settings.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"]
        self.assertTrue(hosts, "channel layer must configure at least one host")
        for host in hosts:
            self.assertIsInstance(
                host, dict,
                "hosts must be dicts so connection kwargs can be passed; a bare "
                "URL string inherits redis-py's 5s socket_timeout default",
            )
            socket_timeout = host.get("socket_timeout")
            self.assertIsNotNone(
                socket_timeout,
                "socket_timeout must be set explicitly, not left to redis-py",
            )
            self.assertGreater(
                socket_timeout,
                RedisChannelLayer.brpop_timeout,
                "socket_timeout must exceed brpop_timeout or idle receives raise "
                "redis.exceptions.TimeoutError",
            )


class BookCoverTests(TestCase):
    """Covers are rendered from the PDF's first page and must keep resolving.

    The URL is signed per request: storing ``storage.url()`` persisted a
    presigned S3/MinIO link that expired after AWS_QUERYSTRING_EXPIRE, so every
    cover broke about an hour after upload.
    """

    def setUp(self):
        from bookshelf.models import Book

        self.user = User.objects.create_user("coverowner", password="pw12345!")
        self.book = Book.objects.create(title="Covered", user=self.user)

    def _pdf_bytes(self):
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "First page content.", fontsize=14)
        data = doc.tobytes()
        doc.close()
        return data

    def _upload_pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.user)
        res = client.post(
            "/files/",
            {
                "book": self.book.id,
                "file": SimpleUploadedFile("doc.pdf", self._pdf_bytes()),
                "order": 0,
            },
            format="multipart",
        )
        self.assertEqual(res.status_code, 201, res.data)
        return client

    def test_pdf_upload_generates_a_cover(self):
        self._upload_pdf()
        self.book.refresh_from_db()
        self.assertTrue(
            self.book.cover_path,
            "uploading a PDF should render its first page into cover_path",
        )

    def test_serializer_exposes_cover_url_from_stored_path(self):
        client = self._upload_pdf()
        res = client.get(f"/books/{self.book.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(
            res.data["cover_url"],
            "the API must expose a usable cover_url for the frontend",
        )

    def test_cover_url_is_regenerated_not_read_from_a_stale_column(self):
        """A stale stored URL must never be served when a path is present."""
        from bookshelf.models import Book
        from bookshelf.serializers import BookSerializer

        stale = "http://stale.invalid/expired-cover.png?Signature=OLD"
        Book.objects.filter(pk=self.book.pk).update(
            cover_path="books/1/cover.png", cover_url=stale,
        )
        data = BookSerializer(Book.objects.get(pk=self.book.pk)).data
        fresh = data["cover_url"] or ""
        # Use a host-based sentinel: a freshly signed S3/MinIO URL carries an
        # "Expires=<epoch>" parameter of its own, so substring-matching on
        # "Expires=" would match the *correct* answer too.
        self.assertNotIn("stale.invalid", fresh)
        self.assertNotEqual(fresh, stale)
        self.assertIn("cover.png", fresh)

    def test_legacy_rows_without_a_path_still_resolve(self):
        from bookshelf.models import Book
        from bookshelf.serializers import BookSerializer

        Book.objects.filter(pk=self.book.pk).update(
            cover_path="", cover_url="http://example.com/legacy.png"
        )
        data = BookSerializer(Book.objects.get(pk=self.book.pk)).data
        self.assertEqual(data["cover_url"], "http://example.com/legacy.png")


class ListeningTimeTests(TestCase):
    """Measured listening time: accumulation, clamping and derived stats."""

    def setUp(self):
        from rest_framework.test import APIClient
        from bookshelf.models import Book

        self.user = User.objects.create_user("listener", password="pw12345!")
        self.book = Book.objects.create(title="L", user=self.user)
        self.client_ = APIClient()
        self.client_.force_authenticate(user=self.user)

    def _report(self, ms, client=None):
        return (client or self.client_).post(
            f"/books/{self.book.id}/listening/", {"ms": ms}, format="json"
        )

    def _stats(self):
        return self.client_.get("/api/stats/").json()

    def test_reports_accumulate_across_calls(self):
        from bookshelf.models import ReadingProgress

        self.assertEqual(self._report(30_000).status_code, 202)
        self.assertEqual(self._report(45_000).status_code, 202)
        row = ReadingProgress.objects.get(user=self.user, book=self.book)
        self.assertEqual(row.listened_ms, 75_000)
        self.assertEqual(self._stats()["listening_ms"], 75_000)

    def test_absurd_and_negative_deltas_are_rejected(self):
        # A stuck client must not be able to inflate the totals without bound.
        self.assertEqual(self._report(10 * 60 * 1000).status_code, 400)
        self.assertEqual(self._report(0).status_code, 400)
        self.assertEqual(self._report(-5000).status_code, 400)
        self.assertEqual(self._stats()["listening_ms"], 0)

    def test_today_and_daily_rollup(self):
        self._report(60_000)
        self._report(30_000)
        stats = self._stats()
        self.assertEqual(stats["listening_today_ms"], 90_000)
        self.assertEqual(stats["days_listened"], 1)
        self.assertEqual(stats["listening_daily_average_ms"], 90_000)

    def test_streak_counts_consecutive_days(self):
        from datetime import timedelta
        from django.utils import timezone
        from bookshelf.models import ListeningDay

        today = timezone.localdate()
        for offset in (0, 1, 2):
            ListeningDay.objects.create(
                user=self.user, date=today - timedelta(days=offset), listened_ms=60_000
            )
        # A gap at day 4 must end the streak at 3.
        ListeningDay.objects.create(
            user=self.user, date=today - timedelta(days=4), listened_ms=60_000
        )
        stats = self._stats()
        self.assertEqual(stats["current_streak_days"], 3)
        self.assertEqual(stats["days_listened"], 4)

    def test_measurement_is_separate_from_the_estimate(self):
        """The measured figure must not be contaminated by the old estimate."""
        from bookshelf.models import Book, ReadingProgress

        book = Book.objects.create(
            title="Estimated", user=self.user, duration_estimate_ms=100_000
        )
        ReadingProgress.objects.create(
            user=self.user, book=book, percent=50.0, listened_ms=0
        )
        stats = self._stats()
        self.assertEqual(stats["estimated_listening_ms"], 50_000)
        self.assertEqual(stats["listening_ms"], 0)

    def test_requires_authentication(self):
        from rest_framework.test import APIClient

        self.assertIn(self._report(1000, client=APIClient()).status_code, (401, 403))


class TtsChunkingTests(TestCase):
    """Every synthesis request must stay under the provider's limits.

    LINEAR_PCM at 44.1 kHz mono is ~86 KB/s, so gRPC's 4 MB default receive
    limit is reached after only ~48s of speech. A single long paragraph blew
    it with "RESOURCE_EXHAUSTED: Received message larger than max".
    """

    def _service(self):
        from bookshelf.tts.nvidia import NvidiaTTSService

        return NvidiaTTSService()

    def test_chunks_respect_the_per_request_cap(self):
        svc = self._service()
        cap = svc.max_chars_per_request
        text = "This is a sentence about startups. " * 200
        for chunk in svc.chunk_text(text, max_bytes=cap):
            self.assertLessEqual(len(chunk.encode("utf-8")), cap)

    def test_a_single_oversized_sentence_is_hard_split(self):
        """Sentence-boundary splitting alone leaves over-long sentences whole."""
        svc = self._service()
        cap = svc.max_chars_per_request
        # No sentence punctuation at all: one "sentence" far over the cap.
        text = ("word " * 1500).strip()
        chunks = svc.chunk_text(text, max_bytes=cap)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.encode("utf-8")), cap)
        # No words may be lost or duplicated by the split.
        self.assertEqual(" ".join(chunks).split(), text.split())

    def test_cap_keeps_audio_under_the_grpc_ceiling(self):
        from bookshelf.tts.nvidia import MAX_GRPC_RECEIVE_BYTES

        svc = self._service()
        # Pessimistic: ~8 chars/second of speech (slow, heavily normalised).
        worst_seconds = svc.max_chars_per_request / 8
        worst_bytes = worst_seconds * svc.sample_rate_hz * svc.SAMPLE_WIDTH_BYTES
        self.assertLess(
            worst_bytes, MAX_GRPC_RECEIVE_BYTES,
            "a single request could still exceed the gRPC receive limit",
        )

    def test_short_text_is_a_single_request(self):
        svc = self._service()
        self.assertEqual(svc.chunk_text("Hello world.", max_bytes=1500), ["Hello world."])
