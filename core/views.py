import os
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse


def _check_db():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1;")
        cursor.fetchone()


def _env_keys():
    raw = os.getenv("DIAGNOSTICS_ENV_KEYS")
    if raw is None:
        raw = "SECRET_KEY,DATABASE_URL"
    return [key.strip() for key in raw.split(",") if key.strip()]


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
