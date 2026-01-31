import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView as BaseLoginView,
    LogoutView,
    PasswordResetView,
)
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from .forms import (
    LoginForm,
    PasswordResetIdentifierForm,
    ProfileForm,
    SignupForm,
)

logger = logging.getLogger(__name__)


class LoginGateView(BaseLoginView):
    """Вход в систему."""
    
    authentication_form = LoginForm
    template_name = "registration/login.html"
    extra_context = {"hide_nav": True}
    
    def get_success_url(self):
        """Редирект после входа."""
        next_url = self.request.GET.get('next') or self.request.POST.get('next')
        if next_url and self._is_safe_url(next_url):
            return next_url
        return reverse_lazy('dashboard')
    
    def _is_safe_url(self, url):
        from django.utils.http import url_has_allowed_host_and_scheme
        return url_has_allowed_host_and_scheme(url, allowed_hosts=[self.request.get_host()])
    
    def form_valid(self, form):
        user = form.get_user()
        messages.success(self.request, f"Добро пожаловать, {user.first_name or user.username}!")
        return super().form_valid(form)


class LogoutAllowGetView(LogoutView):
    """Разрешить выход через GET."""
    http_method_names = ["get", "head", "options", "post"]


class SignupView(CreateView):
    """
    Быстрая регистрация.
    Пользователь создается активным и сразу авторизуется (Auto-Login).
    Никаких подтверждений почты.
    """
    
    model = get_user_model()
    form_class = SignupForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("dashboard") 
    extra_context = {"hide_nav": True}

    def form_valid(self, form):
        try:
            # 1. Сохраняем пользователя, но пока не коммитим в базу
            user = form.save(commit=False)
            user.is_active = True  # Сразу активен
            user.save()
            
            # --- ВАЖНОЕ ИСПРАВЛЕНИЕ ---
            # CreateView требует, чтобы self.object был установлен
            self.object = user 
            # --------------------------

            # Сохраняем m2m (если были теги или группы)
            if hasattr(form, 'save_m2m'):
                form.save_m2m()
            
            logger.info(f"Пользователь создан: {user.username}")
            
            # 2. АВТОМАТИЧЕСКИЙ ВХОД (Auto-Login)
            login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')

            messages.success(
                self.request,
                f"Добро пожаловать, {user.first_name or user.username}! Вы успешно зарегистрированы."
            )
            
            # 3. Редирект в дашборд
            return HttpResponseRedirect(self.get_success_url())
            
        except IntegrityError as e:
            logger.error(f"IntegrityError: {e}")
            form.add_error(None, "Ошибка: Пользователь с такими данными уже существует.")
            return self.form_invalid(form)
            
        except Exception as e:
            logger.error(f"Signup Error: {e}", exc_info=True)
            form.add_error(None, "Произошла ошибка при регистрации. Попробуйте позже.")
            return self.form_invalid(form)


class PasswordResetGateView(PasswordResetView):
    """Форма восстановления пароля."""
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    html_email_template_name = "registration/password_reset_email_html.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")
    extra_context = {"hide_nav": True}
    form_class = PasswordResetIdentifierForm


class ProfileView(LoginRequiredMixin, UpdateView):
    """Профиль пользователя."""
    model = get_user_model()
    form_class = ProfileForm
    template_name = "registration/profile.html"
    success_url = reverse_lazy("profile")

    def get_object(self, queryset=None):
        return self.request.user