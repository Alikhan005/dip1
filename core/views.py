import os
from io import BytesIO
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST


def _check_db():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1;")
        cursor.fetchone()


def _env_keys():
    raw = os.getenv("DIAGNOSTICS_ENV_KEYS")
    if raw is None:
        raw = "DJANGO_SECRET_KEY,DATABASE_URL"
    return [key.strip() for key in raw.split(",") if key.strip()]


def _can_access_diagnostics(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or getattr(user, "role", "") == "admin"
    )


def healthz(request):
    checks = {
        "status": "ok",
        "db": "ok",
        "debug": settings.DEBUG,
    }

    try:
        _check_db()
    except Exception as exc:
        checks["status"] = "fail"
        checks["db"] = f"fail: {type(exc).__name__}: {exc}"

    code = 200 if checks["status"] == "ok" else 500
    return JsonResponse(checks, status=code)


def diagnostics(request):
    if not _can_access_diagnostics(request.user):
        return JsonResponse({"status": "forbidden"}, status=403)

    result = {
        "status": "ok",
        "checks": {},
        "debug": settings.DEBUG,
    }

    def fail(name, msg):
        result["status"] = "fail"
        result["checks"][name] = f"fail: {msg}"

    keys = _env_keys()
    if not keys:
        result["checks"]["env"] = "skip"
    else:
        missing = [key for key in keys if not os.getenv(key)]
        if missing:
            fail("env", f"missing {', '.join(missing)}")
        else:
            result["checks"]["env"] = "ok"

    db_ok = True
    try:
        _check_db()
        result["checks"]["db"] = "ok"
    except Exception as exc:
        db_ok = False
        fail("db", f"{type(exc).__name__}: {exc}")

    if db_ok:
        try:
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if plan:
                pending = [f"{m.app_label}.{m.name}" for m, _ in plan][:10]
                msg = "pending " + ", ".join(pending)
                if len(plan) > len(pending):
                    msg += f" (+{len(plan) - len(pending)} more)"
                fail("migrations", msg)
            else:
                result["checks"]["migrations"] = "ok"
        except Exception as exc:
            fail("migrations", f"{type(exc).__name__}: {exc}")
    else:
        result["checks"]["migrations"] = "skip: db unavailable"

    try:
        path = Path(settings.MEDIA_ROOT) / "diag_test.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok", encoding="utf-8")
        path.unlink(missing_ok=True)
        result["checks"]["media"] = "ok"
    except Exception as exc:
        fail("media", f"{type(exc).__name__}: {exc}")

    try:
        from weasyprint import HTML  # type: ignore

        buffer = BytesIO()
        HTML(string="<html><body>ok</body></html>").write_pdf(target=buffer)
        if buffer.getbuffer().nbytes == 0:
            fail("pdf", "empty output")
        else:
            result["checks"]["pdf"] = "ok"
    except Exception as exc:
        fail("pdf", f"{type(exc).__name__}: {exc}")

    code = 200 if result["status"] == "ok" else 500
    return JsonResponse(result, status=code)


@login_required
def workflow_guide(request):
    return render(request, "guide/workflow_guide.html")


@login_required
@require_POST
def mark_notifications_read(request):
    from config.views import _count_unread_notifications, _latest_notification_changed_at
    from core.models import NotificationState

    state, _ = NotificationState.objects.get_or_create(user=request.user)
    latest_changed_at = _latest_notification_changed_at(request.user)

    if latest_changed_at is None:
        if state.last_seen_at is None:
            state.last_seen_at = timezone.now()
            state.save(update_fields=["last_seen_at", "updated_at"])
    elif state.last_seen_at is None or latest_changed_at > state.last_seen_at:
        state.last_seen_at = latest_changed_at
        state.save(update_fields=["last_seen_at", "updated_at"])

    unread_count = _count_unread_notifications(request.user, state.last_seen_at)
    return JsonResponse({"ok": True, "unread_count": unread_count})
