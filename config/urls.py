from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import (
    LoginGateView,
    LogoutAllowGetView,
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
    path("accounts/", include("django.contrib.auth.urls")),
    path("dashboard/", dashboard, name="dashboard"),
    path("", include("core.urls")),
    path("", include("catalog.urls")),
    path("syllabi/", include("syllabi.urls")),
    path("", include("ai_checker.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
