from django.shortcuts import render
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.decorators import method_decorator

from rest_framework import viewsets, permissions, pagination, filters, response, status
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter

#from core.mixins import CacheResponseMixin
from permissions import IsBookCreator, IsFileAuthor, PublicOrPrivate
from scripts.pdf_converter import PdfExtractor

from .filters import BookFileFilter
from .models import BookFile, Book
from .serializers import BookFileSerializer, BookSerializer

# Create your views here.


class BookViewSet(viewsets.ModelViewSet): #, CacheResponseMixin):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    pagination_class = pagination.LimitOffsetPagination
    permission_classes = [permissions.AllowAny]

    filterset_fields = ["title", "author", "created_at", "updated_at", "status"]
    search_fields = ["title", "author", "description", "status"]
    ordering_fields = ["title", "production_year", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user

        if user.is_authenticated:
            return Book.objects.filter(Q(user=user) | Q(status="public"))

        return Book.objects.filter(status="public")

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsBookCreator()]

        elif self.action in ["read_page", "all_page"]:
            return [PublicOrPrivate()]

        return super().get_permissions()


    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(
            parameters=[OpenApiParameter("page", type=int, description="the pdf page to be displayed")]
    )
    @action(detail=True, methods=['get'], url_path="read-page", url_name="read_page")
    def read_one_page(self, request, pk=None):

        page_number=request.query_params.get('page')
        if not page_number:
            return response.Response(status=status.HTTP_400_BAD_REQUEST)

        book = self.get_object()
        file = book.files.first()

        if not file:
            return response.Response(data="pdf file not found", status=status.HTTP_404_NOT_FOUND)

        pdf_processor = PdfExtractor(file.file.path)

        page_content = pdf_processor.get_one_page(int(page_number))

        page = response.Response(data={int(page_number): page_content}, status=status.HTTP_200_OK)
        return page
     

    @action(detail=True, methods=['get'], url_path="pages", url_name="all_page", permission_classes=[permissions.AllowAny])
    def read_all_pages(self, request, pk=None, *args, **kwargs):


        book = self.get_object()
        file = book.files.first()

        if not file:
            return response.Response(data="pdf file not found", status=status.HTTP_404_NOT_FOUND)

        pdf_processor = PdfExtractor(file.file.path)

        page = pdf_processor.get_all_pages()

        page = response.Response(data=page, status=status.HTTP_200_OK)
        return page


class BookFileViewSet(viewsets.ModelViewSet): #, CacheResponseMixin):
    queryset = BookFile.objects.all()
    serializer_class = BookFileSerializer
    pagination_class = pagination.LimitOffsetPagination
    permission_class = [permissions.AllowAny]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = BookFileFilter
    ordering_fields = ["book__title", "file", "book__status", "book__created_at"]

    def get_queryset(self):
        user = self.request.user
        
        if user.is_authenticated:
            return BookFile.objects.filter(Q(book__user=user) | Q(book__status="public"))
        
        return BookFile.objects.filter(book__status="public")

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsFileAuthor()]

        return super().get_permissions()

""" {
  "title": "Harry Potter and the Prisoner of Azkaban",
  "description": "Harry Potter and the Prisoner of Azkaban is the third novel in the Harry Potter franchise written by JK Rowling from 1997 to 2007 ",
  "author": "JK Rowling",
  "production_year": 2004,
  "status": "private"
} """