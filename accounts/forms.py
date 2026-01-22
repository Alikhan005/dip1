from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate

User = get_user_model()


class SignupForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.existing_user = None
        allowed_role_values = {
            User.Role.TEACHER,
            User.Role.PROGRAM_LEADER,
            User.Role.DEAN,
            User.Role.UMU,
        }
        allowed_roles = [choice for choice in User.Role.choices if choice[0] in allowed_role_values]
        self.fields["role"].choices = allowed_roles
        self.fields["email"].required = True

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "faculty",
            "department",
            "password1",
            "password2",
        )
        labels = {
            "first_name": "Имя",
            "last_name": "Фамилия",
            "role": "Роль в системе",
            "faculty": "Факультет",
            "department": "Кафедра",
        }
        help_texts = {
            "role": "Выберите свою роль. При необходимости администратор сможет изменить её позже.",
        }

    def _set_existing_user(self, user):
        if self.existing_user and self.existing_user.pk != user.pk:
            raise ValidationError(
                "Имя пользователя и email уже заняты разными аккаунтами. Проверьте данные."
            )
        self.existing_user = user
        self.instance = user

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            return username

        existing = User.objects.filter(username__iexact=username).first()
        if existing:
            if existing.is_active or existing.email_verified:
                raise ValidationError("Пользователь с таким именем уже существует.")
            self._set_existing_user(existing)
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            raise ValidationError("Введите email.")

        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            if existing.is_active or existing.email_verified:
                raise ValidationError("Пользователь с таким email уже существует.")
            self._set_existing_user(existing)
        return email


class LoginForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].label = "Имя пользователя или email"
        self.fields["username"].widget.attrs["placeholder"] = "логин или email"
        self.error_messages["invalid_login"] = "Введите корректный логин/email и пароль."

    def clean(self):
        username_or_email = (self.cleaned_data.get("username") or "").strip()
        password = self.cleaned_data.get("password")

        lookup_username = username_or_email
        if username_or_email and "@" in username_or_email:
            user = User.objects.filter(email__iexact=username_or_email).first()
            if user:
                lookup_username = user.username

        self.cleaned_data["username"] = lookup_username
        user = authenticate(self.request, username=lookup_username, password=password)
        if user is None:
            raise ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )

        self.confirm_login_allowed(user)
        # AuthenticationForm expects user_cache for LoginView to log in.
        self.user_cache = user
        return self.cleaned_data

    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise ValidationError(
                "Аккаунт не активирован. Подтвердите email или обратитесь к администратору."
            )


class PasswordResetIdentifierForm(PasswordResetForm):
    email = forms.CharField(
        label="Email или логин",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "Email или логин",
            }
        ),
    )


class EmailVerificationForm(forms.Form):
    email = forms.EmailField(label="Email")
    code = forms.CharField(label="Код подтверждения", max_length=6)

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").replace(" ", "").strip()
        if not code.isdigit() or len(code) != 6:
            raise ValidationError("Введите 6 цифр.")
        return code


class ResendEmailForm(forms.Form):
    email = forms.EmailField(label="Email")


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "faculty", "department")
        labels = {
            "first_name": "Имя",
            "last_name": "Фамилия",
            "email": "Email",
            "faculty": "Факультет",
            "department": "Кафедра",
        }
