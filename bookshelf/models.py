from django.db import models
from django.conf import settings
from enum import Enum

class BookStatus(Enum):
    PUBLIC = "public"
    PRIVATE = "private"

BOOK_STATUS = [
    (BookStatus.PUBLIC, "Public"),
    (BookStatus.PRIVATE, "Private"),
]


# Create your models here.
class Book(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="books", on_delete=models.CASCADE
    )
    # book_password = models.CharField(max_length=150, blank=True, null=True)
    author = models.CharField(max_length=255, blank=True, null=True)

    production_year = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=BOOK_STATUS, default=BookStatus.PRIVATE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


# TODO: make a model for the book cover image.
# Just get a screen shot of the first page of the file

""" class BookCover(models.Model):
    book = models.ForeignKey(Book, related_name='files', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=None, height_field=None, width_field=None, max_length=100) """


def handle_file_upload(instance, filename):
    return f"books/{instance.book.title}/{filename}"


class BookFile(models.Model):
    book = models.ForeignKey(Book, related_name="files", on_delete=models.CASCADE)
    file = models.FileField(upload_to=handle_file_upload)

    def __str__(self):
        return f"{self.book.title} - {self.file}"
