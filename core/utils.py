from django.core.cache import cache
from django.conf import settings


""" # cache_utils
CACHE_TTL = getattr(settings, "CACHE_TTL", 60 * 15)


def get_cache_key(view_name, *args):
    return f'{view_name}-{"-".join(map(str, args))}'


def cache_response(key, response):
    cache.set(key, response, CACHE_TTL)


def get_cached_response(key):
    return cache.get(key)


def delete_cache(key):
    cache.delete(key) """
