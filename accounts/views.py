import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView as BaseLoginView,
    LogoutView,
    PasswordResetView,
)
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView

from .forms import (
    EmailVerificationForm,
    LoginForm,
    PasswordResetIdentifierForm,
    ProfileForm,
    ResendEmailForm,
    SignupForm,
)
from .services import (
    can_resend,
    create_or_refresh_verification,
    resolve_from_email,
    send_verification_email,
)

VERIFY_SESSION_KEY = "pending_user_id"
logger = logging.getLogger(__name__)


class LoginGateView(BaseLoginView):
    """Login screen with a minimal layout."""

    extra_context = {"hide_nav": True}
    authentication_form = LoginForm

    def form_invalid(self, form):
        identifier = (form.data.get("username") or "").strip()
        password = form.data.get("password") or ""
        if identifier and password:
            user = (
                get_user_model()
                .objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))
                .first()
            )
            if user and user.check_password(password) and not user.is_active:
                verification = getattr(user, "email_verification", None)
                try:
                    if verification and not can_resend(verification):
                        messages.warning(
                            self.request,
                            "Код уже отправлен. Подождите минуту и попробуйте снова.",
                        )
                    else:
                        code, ttl_minutes = create_or_refresh_verification(user, verification)
                        try:
                            send_verification_email(user, code, ttl_minutes)
                            messages.info(
                                self.request,
                                "Аккаунт не активирован. Мы отправили код подтверждения.",
                            )
                        except Exception:
                            logger.exception(
                                "Failed to send verification email for user_id=%s",
                                user.pk,
                            )
                            messages.error(
                                self.request,
                                "Не удалось отправить письмо с кодом. Попробуйте позже.",
                            )
                    self.request.session[VERIFY_SESSION_KEY] = user.pk
                    return redirect("verify_email")
                except Exception:
                    logger.exception(
                        "Failed to prepare verification code for user_id=%s",
                        user.pk,
                    )
                    messages.error(
                        self.request,
                        "Не удалось подготовить код подтверждения. Попробуйте позже.",
                    )
        return super().form_invalid(form)


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
            existing_user = getattr(form, "existing_user", None)
            if existing_user:
                user = existing_user
                user.username = form.cleaned_data["username"]
                user.first_name = form.cleaned_data["first_name"]
                user.last_name = form.cleaned_data["last_name"]
                user.email = form.cleaned_data["email"]
                user.role = form.cleaned_data["role"]
                user.faculty = form.cleaned_data["faculty"]
                user.department = form.cleaned_data["department"]
                user.set_password(form.cleaned_data["password1"])
                user.is_active = False
                user.email_verified = False
                user.save()
            else:
                user = form.save(commit=False)
                user.is_active = False
                user.email_verified = False
                user.save()
                form.save_m2m()

            code, ttl_minutes = create_or_refresh_verification(user)
            try:
                send_verification_email(user, code, ttl_minutes)
                if existing_user:
                    messages.info(
                        self.request,
                        "Аккаунт уже создан. Мы отправили новый код подтверждения на почту.",
                    )
                else:
                    messages.success(
                        self.request,
                        "Мы отправили код подтверждения на почту. Введите его для активации аккаунта.",
                    )
            except Exception:
                logger.exception(
                    "Failed to send verification email for user_id=%s",
                    user.pk,
                )
                messages.error(
                    self.request,
                    "Не удалось отправить письмо с кодом. Попробуйте позже.",
                )

            self.request.session[VERIFY_SESSION_KEY] = user.pk
            return redirect("verify_email")
        except IntegrityError:
            username = (form.cleaned_data.get("username") or "").strip()
            email = (form.cleaned_data.get("email") or "").strip()
            if username and get_user_model().objects.filter(username__iexact=username).exists():
                form.add_error("username", "Пользователь с таким именем уже существует.")
            if email and get_user_model().objects.filter(email__iexact=email).exists():
                form.add_error("email", "Пользователь с таким email уже существует.")
            if not form.errors:
                form.add_error(None, "Не удалось создать аккаунт. Проверьте данные и попробуйте снова.")
            return self.form_invalid(form)


class PasswordResetGateView(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    html_email_template_name = "registration/password_reset_email_html.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")
    extra_context = {"hide_nav": True}
    form_class = PasswordResetIdentifierForm

    def form_valid(self, form):
        self.from_email = resolve_from_email()
        identifier = (form.cleaned_data.get("email") or "").strip()
        user_model = get_user_model()
        email = identifier
        if identifier and "@" not in identifier:
            user = user_model.objects.filter(username__iexact=identifier).first()
            if not user or not user.email:
                form.add_error("email", "Пользователь с таким email или логином не найден.")
                return self.form_invalid(form)
            email = user.email

        users = list(user_model.objects.filter(email__iexact=email))
        if not users:
            form.add_error("email", "Пользователь с таким email или логином не найден.")
            return self.form_invalid(form)
        form.cleaned_data["email"] = email

        active_exists = any(user.is_active for user in users)
        inactive_user = next(
            (user for user in users if not user.is_active and not user.email_verified),
            None,
        )
        if inactive_user and not active_exists:
            try:
                code, ttl_minutes = create_or_refresh_verification(inactive_user)
            except Exception:
                logger.exception(
                    "Failed to prepare verification code for user_id=%s",
                    inactive_user.pk,
                )
                form.add_error(
                    None,
                    "Не удалось подготовить код подтверждения. Попробуйте позже.",
                )
                return self.form_invalid(form)
            try:
                send_verification_email(inactive_user, code, ttl_minutes)
                messages.info(
                    self.request,
                    "Аккаунт не активирован. Мы отправили код подтверждения на почту.",
                )
            except Exception:
                logger.exception(
                    "Failed to send verification email for user_id=%s",
                    inactive_user.pk,
                )
                messages.error(
                    self.request,
                    "Не удалось отправить письмо с кодом. Попробуйте позже.",
                )
            self.request.session[VERIFY_SESSION_KEY] = inactive_user.pk
            return redirect("verify_email")

        try:
            return super().form_valid(form)
        except Exception:
            logger.exception("Failed to send password reset email for %s", email)
            form.add_error(
                None,
                "Не удалось отправить письмо для восстановления. Проверьте настройки почты и попробуйте позже.",
            )
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
        logger.exception(
            "Failed to send verification email for user_id=%s",
            user.pk,
        )
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
