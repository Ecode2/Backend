import os
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import BookFile, Book


@receiver(post_delete, sender=Book)
def delete_book_file(sender, instance, **kwargs):
    book_files = BookFile.objects.filter(book=instance)

    for book_file in book_files:
        if book_file.file:
            if os.path.isfile(book_file.file.path):
                os.remove(book_file.file.path)

            book_file.delete()
