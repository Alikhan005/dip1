from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as BaseLoginView, LogoutView
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView

from .forms import EmailVerificationForm, LoginForm, ProfileForm, ResendEmailForm, SignupForm
from .services import can_resend, create_or_refresh_verification, send_verification_email

VERIFY_SESSION_KEY = "pending_user_id"


class LoginGateView(BaseLoginView):
    """Login screen with a minimal layout."""

    extra_context = {"hide_nav": True}
    authentication_form = LoginForm


class LogoutAllowGetView(LogoutView):
    """Allow logout via GET for UX parity with legacy behavior."""

    http_method_names = ["get", "head", "options", "post"]


class SignupView(CreateView):
    model = get_user_model()
    form_class = SignupForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")
    extra_context = {"hide_nav": True}

    def form_valid(self, form):
        try:
            user = form.save(commit=False)
            user.is_active = False
            user.email_verified = False
            user.save()
            form.save_m2m()

            code, ttl_minutes = create_or_refresh_verification(user)
            try:
                send_verification_email(user, code, ttl_minutes)
                messages.success(
                    self.request,
                    "Мы отправили код подтверждения на почту. Введите его для активации аккаунта.",
                )
            except Exception:
                messages.error(
                    self.request,
                    "Не удалось отправить письмо с кодом. Попробуйте позже.",
                )

            self.request.session[VERIFY_SESSION_KEY] = user.pk
            return redirect("verify_email")
        except IntegrityError:
            form.add_error("username", "Пользователь с таким именем уже существует.")
            return self.form_invalid(form)


def verify_email(request):
    user_model = get_user_model()
    pending_user = None
    pending_email = ""
    pending_id = request.session.get(VERIFY_SESSION_KEY)
    if pending_id:
        pending_user = user_model.objects.filter(pk=pending_id).first()
        if pending_user:
            pending_email = pending_user.email or ""

    if request.method == "POST":
        form = EmailVerificationForm(request.POST, initial={"email": pending_email})
        if form.is_valid():
            email = form.cleaned_data["email"]
            code = form.cleaned_data["code"]
            user = user_model.objects.filter(email__iexact=email).first()
            if not user:
                form.add_error("email", "Пользователь с таким email не найден.")
            elif user.email_verified:
                messages.info(request, "Email уже подтвержден. Войдите в аккаунт.")
                return redirect("login")
            else:
                verification = getattr(user, "email_verification", None)
                if verification is None:
                    form.add_error(None, "Код не найден. Запросите новый.")
                elif verification.is_expired():
                    form.add_error("code", "Срок кода истек. Запросите новый.")
                elif not verification.check_code(code):
                    verification.attempts += 1
                    verification.save(update_fields=["attempts"])
                    form.add_error("code", "Неверный код.")
                else:
                    verification.mark_verified()
                    verification.save(update_fields=["verified_at"])
                    user.email_verified = True
                    user.is_active = True
                    user.save(update_fields=["email_verified", "is_active"])
                    request.session.pop(VERIFY_SESSION_KEY, None)
                    messages.success(request, "Email подтвержден. Теперь можно войти.")
                    return redirect("login")
    else:
        form = EmailVerificationForm(initial={"email": pending_email})

    return render(request, "registration/verify_email.html", {"form": form, "hide_nav": True})


@require_POST
def resend_email_code(request):
    form = ResendEmailForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Введите корректный email.")
        return redirect("verify_email")

    email = form.cleaned_data["email"]
    user = get_user_model().objects.filter(email__iexact=email).first()
    if not user:
        messages.error(request, "Пользователь с таким email не найден.")
        return redirect("verify_email")
    if user.email_verified:
        messages.info(request, "Email уже подтвержден. Войдите в аккаунт.")
        return redirect("login")

    verification = getattr(user, "email_verification", None)
    if verification and not can_resend(verification):
        messages.warning(request, "Подождите немного перед повторной отправкой кода.")
        return redirect("verify_email")

    code, ttl_minutes = create_or_refresh_verification(user, verification)
    try:
        send_verification_email(user, code, ttl_minutes)
        messages.success(request, "Новый код отправлен на почту.")
    except Exception:
        messages.error(request, "Не удалось отправить письмо с кодом. Попробуйте позже.")

    request.session[VERIFY_SESSION_KEY] = user.pk
    return redirect("verify_email")


class ProfileView(LoginRequiredMixin, UpdateView):
    model = get_user_model()
    form_class = ProfileForm
    template_name = "registration/profile.html"
    success_url = reverse_lazy("profile")

    def get_object(self, queryset=None):
        return self.request.user
