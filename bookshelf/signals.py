import os
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.core.cache import cache
from .models import BookFile, Book


@receiver(post_delete, sender=Book)
def delete_book_file(sender, instance, **kwargs):
    book_files = BookFile.objects.filter(book=instance)

    for book_file in book_files:
        if book_file.file:
            try:
                if os.path.isfile(book_file.file.path):
                    os.remove(book_file.file.path)

                book_file.delete()
            except Exception as e:
                pass

@receiver(post_save, sender=Book)
def invalidate_book_cache_on_save(sender, instance, **kwargs):
    cache.delete_pattern('book_shelf:*')

@receiver(post_delete, sender=Book)
def invalidate_book_cache_on_delete(sender, instance, **kwargs):
    cache.delete_pattern('book_shelf:*')

@receiver(post_save, sender=BookFile)
def invalidate_bookfile_cache_on_save(sender, instance, **kwargs):
    cache.delete_pattern('book_shelf:*')  

@receiver(post_delete, sender=BookFile)
def invalidate_bookfile_cache_on_delete(sender, instance, **kwargs):
    cache.delete_pattern('book_shelf:*')