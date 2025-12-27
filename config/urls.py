from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import include, path

from accounts.views import LogoutAllowGetView, ProfileView, SignupView
from .views import dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "",
        LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="home",
    ),
    path("accounts/logout/", LogoutAllowGetView.as_view(), name="logout"),
    path("accounts/signup/", SignupView.as_view(), name="signup"),
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
