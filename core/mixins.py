from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.conf import settings
from rest_framework import permissions, mixins, decorators, status
from rest_framework.response import Response
#from .utils import cache_response, get_cached_response, delete_cache, get_cache_key

from .permissions import IsAdminOrStaff
from django.contrib.auth.mixins import LoginRequiredMixin

""" CACHE_TTL = settings.CACHE_TTL

class CachedViewSetMixin:
    @method_decorator(cache_page(CACHE_TTL))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs) """


class AdminStaffRequiredMixin:
    permission_classes = [
        IsAdminOrStaff,
    ]


""" class CacheResponseMixin:
    def list(self, request, *args, **kwargs):
        cache_key = get_cache_key(self.__class__.__name__, "list")
        cached_response = get_cached_response(cache_key)
        if cached_response:
            return Response(cached_response)

        response = super().list(request, *args, **kwargs)
        cache_response(cache_key, response.data)
        return response

    def retrieve(self, request, *args, **kwargs):
        cache_key = get_cache_key(self.__class__.__name__, "retrieve", kwargs.get("pk"))
        cached_response = get_cached_response(cache_key)
        if cached_response:
            return Response(cached_response)

        response = super().retrieve(request, *args, **kwargs)
        cache_response(cache_key, response.data)
        return response

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            self.clear_cache()
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            self.clear_cache()
        return response

    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            self.clear_cache()
        return response

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == status.HTTP_204_NO_CONTENT:
            self.clear_cache()
        return response

    def clear_cache(self):
        list_cache_key = get_cache_key(self.__class__.__name__, "list")
        retrieve_cache_key = get_cache_key(
            self.__class__.__name__, "retrieve", self.kwargs.get("pk")
        )
        delete_cache(list_cache_key)
        delete_cache(retrieve_cache_key)

    def cache_custom_method(self, request, *args, **kwargs):
        if request.method == "GET":
            method_name = self.action  # This will get the name of the custom method
            cache_key = get_cache_key(self.__class__.__name__, method_name, *args)
            cached_response = get_cached_response(cache_key)
            if cached_response:
                return Response(cached_response)

            response = super().custom_method(
                request, *args, **kwargs
            )  # Replace `custom_method` with actual method name
            if request.method == "GET":
                cache_response(cache_key, response.data)
            return response
        else:
            self.clear_cache()
            return super().custom_method(
                request, *args, **kwargs
            )  # Replace `custom_method` with actual method name
 """