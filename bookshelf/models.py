import base64
from io import BytesIO
from django.db import models
from django.conf import settings

from scripts.pdf_converter import PdfExtractor

PUBLIC = "public"
PRIVATE = "private"

BOOK_STATUS = [
    (PUBLIC, "Public"),
    (PRIVATE, "Private"),
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
    status = models.CharField(max_length=20, choices=BOOK_STATUS, default=PRIVATE)

    total_page = models.IntegerField(null=True, blank=True, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def update_total_pages(self):
        first_file = self.files.first()
        if first_file:
            pdf_processor = PdfExtractor(first_file.file.path)
            self.total_page = pdf_processor.get_total_page_number()
            self.save()

    def get_book_cover(self):
        first_file = self.files.first()

        if first_file:
            pdf_processor = PdfExtractor(first_file.file.path)
            img = pdf_processor.get_fist_page_image()

            buffered = BytesIO()
            img.save(buffered, format='WEBP')
            buffered.seek(0)

            img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return f'data:image/webp;base64,{img_base64}'
        return None


def handle_file_upload(instance, filename):
    return f"books/{instance.book.id}/{filename}"


class BookFile(models.Model):
    book = models.ForeignKey(Book, related_name="files", on_delete=models.CASCADE)
    file = models.FileField(upload_to=handle_file_upload)

    def __str__(self):
        return f"{self.book.title} - {self.file}"
