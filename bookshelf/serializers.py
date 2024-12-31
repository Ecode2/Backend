import base64
from io import BytesIO

from django.contrib.auth.models import User
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, OpenApiTypes

from scripts.pdf_converter import PdfExtractor

from .models import Book, BookFile


class BookSerializer(serializers.ModelSerializer):
    book_cover = serializers.SerializerMethodField()
    #pdf_contents = serializers.SerializerMethodField()
    user = serializers.StringRelatedField()

    class Meta:
        model = Book
        fields = ["id", "title", "description", "user", "author", "production_year", "status", "updated_at", "created_at", 'book_cover'] #, 'pdf_contents']
        read_only_fields = ["id", "created_at"]


    def get_book_cover(self, obj):

        first_file = obj.files.first()

        if first_file:
            pdf_processor = PdfExtractor(first_file.file.path)
            img = pdf_processor.get_fist_page_image()

            buffered = BytesIO()
            img.save(buffered, format='WEBP')
            buffered.seek(0)

            img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return f'data:image/webp;base64,{img_base64}'
        return None
    
    """
    def get_pdf_contents(self, obj):
        first_file = obj.files.first()

        if first_file:
            pdf_processor = PdfExtractor(first_file.file.path)
            return pdf_processor.get_all_pages()
        return None """
    


class BookFileSerializer(serializers.ModelSerializer):
    file = serializers.FileField()

    @extend_schema_field(OpenApiTypes.BINARY)
    def get_file(self, obj):
        return obj.file

    class Meta:
        model = BookFile
        fields = ["id", "book", "file"]
        read_only_fields = ["id"]
