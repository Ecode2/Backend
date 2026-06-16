"""Signals: storage cleanup and cache invalidation.

File deletion goes through the storage backend (works for both local FS and
S3/MinIO); the old code assumed ``file.path`` which only exists on local FS.
"""

import logging

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Book, BookFile

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=BookFile)
def delete_book_file_object(sender, instance, **kwargs):
    """Remove the underlying storage object when a BookFile row is deleted."""
    if not instance.file:
        return
    try:
        instance.file.delete(save=False)
    except Exception:  # pragma: no cover - best-effort cleanup
        logger.exception("failed to delete stored file for %s", instance.pk)


def _invalidate_book_cache(*_args, **_kwargs):
    try:
        cache.delete_pattern("book_shelf:*")
    except Exception:  # pragma: no cover - cache backend may not support patterns
        pass


post_save.connect(_invalidate_book_cache, sender=Book)
post_delete.connect(_invalidate_book_cache, sender=Book)
post_save.connect(_invalidate_book_cache, sender=BookFile)
post_delete.connect(_invalidate_book_cache, sender=BookFile)
