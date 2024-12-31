from django_filters import rest_framework as filters
from django.db import models
from .models import BookFile


class BookFileFilter(filters.FilterSet):
    class Meta:
        model = BookFile
        fields = {
            "book": ["exact"],
            "file": ["exact"],
        }
        filter_overrides = {models.FileField: {"filter_class": filters.CharFilter}}
