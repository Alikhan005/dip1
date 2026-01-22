from functools import wraps

from django.core.exceptions import PermissionDenied

def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied
            if getattr(request.user, "is_superuser", False):
                return view_func(request, *args, **kwargs)
            if getattr(request.user, "role", None) == "admin":
                return view_func(request, *args, **kwargs)
            if request.user.role not in roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
