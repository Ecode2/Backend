import base64
from io import BytesIO
from django.db import models
from django.conf import settings
from django.core.files.storage import default_storage
import tempfile
from cloudinary_storage.storage import RawMediaCloudinaryStorage
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from scripts.pdf_converter import PdfExtractor

PUBLIC = "public"
PRIVATE = "private"
BOOK_STATUS = [(PUBLIC, "Public"), (PRIVATE, "Private")]
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 10  # 10MB

class Book(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="books", on_delete=models.CASCADE
    )
    author = models.CharField(max_length=255, blank=True, null=True)
    production_year = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=BOOK_STATUS, default=PRIVATE)
    total_page = models.IntegerField(null=True, blank=True, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def update_total_pages(self):
        """Update the total page count using a storage-agnostic approach."""
        first_file = self.files.first()
        if first_file and default_storage.exists(first_file.file.name):
            with default_storage.open(first_file.file.name, 'rb') as pdf_file:
                # Read the file content into a temporary file
                with tempfile.NamedTemporaryFile(delete=True, suffix='.pdf') as tmp_file:
                    tmp_file.write(pdf_file.read())
                    tmp_file.flush()
                    pdf_processor = PdfExtractor(tmp_file.name)
                    self.total_page = pdf_processor.get_total_page_number()
                    self.save()

    def get_book_cover(self):
        """Generate a base64-encoded book cover image in a storage-agnostic way."""
        first_file = self.files.first()
        if first_file and default_storage.exists(first_file.file.name):
            with default_storage.open(first_file.file.name, 'rb') as pdf_file:
                with tempfile.NamedTemporaryFile(delete=True, suffix='.pdf') as tmp_file:
                    tmp_file.write(pdf_file.read())
                    tmp_file.flush()
                    pdf_processor = PdfExtractor(tmp_file.name)
                    img = pdf_processor.get_fist_page_image()
                    if img:
                        buffered = BytesIO()
                        img.save(buffered, format='WEBP')
                        buffered.seek(0)
                        img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                        return f'data:image/webp;base64,{img_base64}'
        return None

def handle_file_upload(instance, filename):
    return f"books/{instance.book.id}/{filename}"

def file_validation(file):
    if not file:
        raise ValidationError("No file selected.")
    if isinstance(file, UploadedFile) and file.size > FILE_UPLOAD_MAX_MEMORY_SIZE:
        raise ValidationError("File shouldn't be larger than 10MB.")

class BookFile(models.Model):
    book = models.ForeignKey(Book, related_name="files", on_delete=models.CASCADE)
    file = models.FileField(
        upload_to=handle_file_upload,
        storage=RawMediaCloudinaryStorage(),
        validators=[file_validation]
    )

    def __str__(self):
        return f"{self.book.title} - {self.file}"