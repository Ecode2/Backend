import base64
from io import BytesIO
import os
import requests
import tempfile
from django.db import models
from django.conf import settings
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

    def _get_pdf_path(self):
        """
        Download the first PDF file from Cloudinary to a temporary local path.
        Returns the path to the temporary file or None if the file cannot be downloaded.
        """
        first_file = self.files.first()
        if first_file:
            # Download the file from Cloudinary using its URL
            response = requests.get(first_file.file.url)
            if response.status_code == 200:
                # Create a temporary file with a '.pdf' suffix
                tmp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
                tmp_file.write(response.content)
                tmp_file.close()  # Close the file so PdfExtractor can open it
                return tmp_file.name
        return None

    def update_total_pages(self):
        """
        Update the total page count using PdfExtractor by processing a temporary local file.
        """
        pdf_path = self._get_pdf_path()
        if pdf_path:
            try:
                pdf_processor = PdfExtractor(pdf_path)
                self.total_page = pdf_processor.get_total_page_number()
                self.save()
            finally:
                os.remove(pdf_path)  # Clean up the temporary file

    def get_book_cover(self):
        """
        Generate a base64-encoded book cover image using PdfExtractor from a temporary local file.
        """
        pdf_path = self._get_pdf_path()
        if pdf_path:
            try:
                pdf_processor = PdfExtractor(pdf_path)
                img = pdf_processor.get_fist_page_image()  # Assuming this is a typo in your code; should be 'first'
                if img:
                    buffered = BytesIO()
                    img.save(buffered, format='WEBP')
                    buffered.seek(0)
                    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    return f'data:image/webp;base64,{img_base64}'
            finally:
                os.remove(pdf_path)  # Clean up the temporary file
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