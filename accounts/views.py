from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from .forms import ProfileForm, SignupForm


class LogoutAllowGetView(LogoutView):
    """Allow logout via GET for UX parity with legacy behavior."""

    http_method_names = ["get", "head", "options", "post"]


class SignupView(CreateView):
    model = get_user_model()
    form_class = SignupForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")


class ProfileView(LoginRequiredMixin, UpdateView):
    model = get_user_model()
    form_class = ProfileForm
    template_name = "registration/profile.html"
    success_url = reverse_lazy("profile")

    def get_object(self, queryset=None):
        return self.request.user
