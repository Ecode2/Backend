"""Tests for the parsing layer (one fixture per format) and the WS protocol."""

import os
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

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
class ReaderConsumerTests(TestCase):
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
