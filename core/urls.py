from django.urls import path

from .views import diagnostics, healthz

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("diagnostics/", diagnostics, name="diagnostics"),
]
