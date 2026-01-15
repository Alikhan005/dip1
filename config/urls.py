from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.urls import include, path
from django.views.static import serve as media_serve

admin.site.site_header = "AlmaU Syllabus Copy Admin"
admin.site.site_title = "AlmaU Syllabus Copy"
admin.site.index_title = "Administration"

from accounts.views import (
    LoginGateView,
    LogoutAllowGetView,
    PasswordResetGateView,
    ProfileView,
    SignupView,
    resend_email_code,
    verify_email,
)
from .views import dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "",
        LoginGateView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=False,
        ),
        name="home",
    ),
    path(
        "accounts/login/",
        LoginGateView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=False,
        ),
        name="login",
    ),
    path("accounts/logout/", LogoutAllowGetView.as_view(), name="logout"),
    path("accounts/signup/", SignupView.as_view(), name="signup"),
    path("accounts/verify/", verify_email, name="verify_email"),
    path("accounts/verify/resend/", resend_email_code, name="resend_email_code"),
    path("accounts/profile/", ProfileView.as_view(), name="profile"),
    path("accounts/password_reset/", PasswordResetGateView.as_view(), name="password_reset"),
    path(
        "accounts/password_reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
            extra_context={"hide_nav": True},
        ),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            extra_context={"hide_nav": True},
        ),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
            extra_context={"hide_nav": True},
        ),
        name="password_reset_complete",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
    path("dashboard/", dashboard, name="dashboard"),
    path("", include("core.urls")),
    path("", include("catalog.urls")),
    path("syllabi/", include("syllabi.urls")),
    path("", include("ai_checker.urls")),
]

def _is_local_dev_host() -> bool:
    local_hosts = {"127.0.0.1", "localhost", "[::1]"}
    if not settings.ALLOWED_HOSTS:
        return True
    return all(host in local_hosts for host in settings.ALLOWED_HOSTS)


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
elif _is_local_dev_host():
    # Local-only fallback so styles load even with DEBUG=False.
    static_prefix = settings.STATIC_URL.lstrip("/")
    media_prefix = settings.MEDIA_URL.lstrip("/")
    if media_prefix:
        urlpatterns += [
            path(
                f"{media_prefix}<path:path>",
                media_serve,
                {"document_root": settings.MEDIA_ROOT},
            )
        ]
    if static_prefix:
        urlpatterns += [
            path(
                f"{static_prefix}<path:path>",
                staticfiles_serve,
                {"insecure": True},
            )
        ]
