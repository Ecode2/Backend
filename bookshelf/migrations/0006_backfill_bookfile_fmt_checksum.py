"""Backfill fmt / checksum / size_bytes / book_type for pre-existing rows."""

from django.db import migrations


def backfill(apps, schema_editor):
    BookFile = apps.get_model("bookshelf", "BookFile")
    Book = apps.get_model("bookshelf", "Book")

    from bookshelf.files import detect_format, is_audio_format, compute_checksum

    for bf in BookFile.objects.all().iterator():
        changed = False
        if not bf.fmt and bf.file:
            bf.fmt = detect_format(bf.file.name)
            changed = True
        if bf.size_bytes is None and bf.file:
            try:
                bf.size_bytes = bf.file.size
                changed = True
            except Exception:
                pass
        if not bf.checksum and bf.file:
            try:
                bf.checksum = compute_checksum(bf.file)
                changed = True
            except Exception:
                pass
        if changed:
            bf.save(update_fields=["fmt", "size_bytes", "checksum"])

        if bf.fmt and is_audio_format(bf.fmt):
            Book.objects.filter(pk=bf.book_id).update(book_type="audiobook")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("bookshelf", "0005_audiosegmentcache_alter_book_options_and_more"),
    ]

    operations = [migrations.RunPython(backfill, noop)]
