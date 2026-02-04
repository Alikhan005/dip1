import os
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем .env автоматически
if load_dotenv:
    for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=True)
            break


def _ensure_sqlite_dir(path_str: str) -> str:
    if path_str and path_str != ":memory:":
        try:
            Path(path_str).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return path_str

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return default or []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _database_from_url(url: str) -> dict:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme == "sqlite":
        path = parsed.path or ""
        if path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        if not path:
            path = ":memory:"
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": _ensure_sqlite_dir(path),
        }
    if scheme in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": (parsed.path or "/").lstrip("/"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
        }
    raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme}")


SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-eay#!&5+t&u54la8ems-zm*nc!6bv5_7_gm*u2@0*q5z$tqsvl",
)

DEBUG = _env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS")


# Приложения

INSTALLED_APPS = [
    # наши приложения
    "core",
    "accounts",
    "catalog",
    "syllabi",
    "workflow",
    "ai_checker",
    "widget_tweaks",  # <-- БИБЛИОТЕКА НА МЕСТЕ, ОТЛИЧНО

    # стандартные django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"


# Шаблоны

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.static",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# База данных

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": _database_from_url(DATABASE_URL)}
else:
    DB_ENGINE = os.getenv("DB_ENGINE", "django.db.backends.sqlite3")
    if DB_ENGINE.endswith("sqlite3"):
        # ИСПРАВЛЕНИЕ: Используем новое имя файла, чтобы избежать конфликтов со старой базой
        DB_NAME = _ensure_sqlite_dir(os.getenv("DB_NAME", str(BASE_DIR / "db_new.sqlite3")))
        DATABASES = {
            "default": {
                "ENGINE": DB_ENGINE,
                "NAME": DB_NAME,
            }
        }
    else:
        DB_NAME = os.getenv("DB_NAME", "almau_syllabus")
        DATABASES = {
            "default": {
                "ENGINE": DB_ENGINE,
                "NAME": DB_NAME,
                "USER": os.getenv("DB_USER", "postgres"),
                "PASSWORD": os.getenv("DB_PASSWORD", "123"),
                "HOST": os.getenv("DB_HOST", "localhost"),
                "PORT": os.getenv("DB_PORT", "5432"),
            }
        }


# Валидация паролей

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Локаль

LANGUAGE_CODE = "ru"

TIME_ZONE = "Asia/Almaty"

USE_I18N = True

USE_TZ = True


# Статика

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Медиа-файлы
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Кастомный пользователь и редиректы логина

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"
LOGIN_URL = "home"

EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = _env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = _env_bool("EMAIL_USE_SSL", False)
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND")
if not EMAIL_BACKEND:
    if EMAIL_HOST:
        EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    else:
        EMAIL_BACKEND = (
            "django.core.mail.backends.console.EmailBackend"
            if DEBUG
            else "django.core.mail.backends.smtp.EmailBackend"
        )

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "").strip()
if not DEFAULT_FROM_EMAIL:
    if EMAIL_HOST_USER:
        DEFAULT_FROM_EMAIL = f"AlmaU Syllabus <{EMAIL_HOST_USER}>"
    else:
        DEFAULT_FROM_EMAIL = "AlmaU Syllabus <noreply@example.com>"

SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
EMAIL_TIMEOUT = _env_int("EMAIL_TIMEOUT", 15)

EMAIL_VERIFICATION_TTL_MINUTES = _env_int("EMAIL_VERIFICATION_TTL_MINUTES", 15)
EMAIL_VERIFICATION_RESEND_SECONDS = _env_int("EMAIL_VERIFICATION_RESEND_SECONDS", 60)
X_FRAME_OPTIONS = 'SAMEORIGIN'