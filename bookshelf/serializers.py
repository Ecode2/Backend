from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, OpenApiTypes
from cloudinary.utils import cloudinary_url
from cloudinary_storage.storage import RawMediaCloudinaryStorage
from .models import Book, BookFile

class BookSerializer(serializers.ModelSerializer):
    book_cover = serializers.SerializerMethodField()
    user = serializers.StringRelatedField()

    class Meta:
        model = Book
        fields = ["id", "title", "description", "user", "author", "production_year", "status", "total_page", "updated_at", "created_at", 'book_cover']
        read_only_fields = ["id", "created_at"]

    def get_book_cover(self, obj):
        first_file = obj.files.first()
        if first_file:
            # Check if Cloudinary is being used
            if isinstance(first_file.file.storage, RawMediaCloudinaryStorage):
                # Extract public ID and generate Cloudinary URL for the first page
                public_id = first_file.file.name.rsplit('.', 1)[0] if '.' in first_file.file.name else first_file.file.name
                cover_url, _ = cloudinary_url(public_id, format="webp", transformation=[{'page': 1}])
                return cover_url
            # Fallback to model method for non-Cloudinary storage
            return obj.get_book_cover()
        return None

class BookFileSerializer(serializers.ModelSerializer):
    file = serializers.FileField()

    @extend_schema_field(OpenApiTypes.BINARY)
    def get_file(self, obj):
        return obj.file

    class Meta:
        model = BookFile
        fields = ["id", "book", "file"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        response = super().create(validated_data)
        response.book.update_total_pages()
        return response
