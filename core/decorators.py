from django.shortcuts import redirect
from functools import wraps


def role_required(role):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.role == role:
                return view_func(request, *args, **kwargs)
            return redirect("no_permission")  # Redirect to a no-permission page

        return _wrapped_view

    return decorator


def admin_staff_role(role):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.role in [
                "admin",
                "staff",
            ]:
                return view_func(request, *args, **kwargs)
            return redirect("no_permission")  # Redirect to a no-permission page

        return _wrapped_view

    return decorator
