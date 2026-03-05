# DEPLOYMENT

## 1. Local run (for demo / development)

### Fast start
1. Run `start_project.bat`.
2. Wait for two consoles:
   - Django server
   - AI worker
3. Open `http://localhost:8000/`.

Important: do not close the AI worker console. If worker is stopped, checks stay in `ai_check`.

### Manual start
```powershell
venv312\Scripts\activate
python manage.py migrate
python manage.py runserver localhost:8000
```

In second console:
```powershell
venv312\Scripts\activate
python manage.py run_worker
```

## 2. Production profile (.env)

Use the prepared template:

```powershell
Copy-Item .env.production.example .env
```

Then edit `.env` and set:
1. Real `DJANGO_SECRET_KEY`
2. Real domain in `DJANGO_ALLOWED_HOSTS`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
3. Real database `DATABASE_URL` (PostgreSQL recommended)
4. Real SMTP credentials
5. AI provider/API settings

## 3. Production validation checklist

Run:
```powershell
python manage.py check --deploy
python manage.py migrate --plan
python manage.py test
python manage.py collectstatic --noinput
```

Expected:
1. `check --deploy` without security warnings
2. `migrate --plan` shows no pending operations
3. Tests are green
4. Static files collected

## 4. Runtime services

Production needs **2 processes**:
1. Web app process (WSGI/ASGI)
2. AI worker process: `python manage.py run_worker`

If worker is down, AI checks are queued but not processed.

## 5. Health checks

Endpoints:
1. `GET /healthz/` (basic health)
2. `GET /diagnostics/` (admin/staff only)

Use these endpoints in your monitoring system.

## 6. Common issues

1. Syllabus stuck in `ai_check`:
   - worker is not running.
2. Email is not sent:
   - SMTP settings are invalid.
3. `DisallowedHost` error:
   - domain is missing in `ALLOWED_HOSTS`.
4. `check --deploy` warnings:
   - security env values are not configured for production.
