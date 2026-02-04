@echo off
title AlmaU Launcher
echo ===================================================
echo   ZAPUSK PROEKTA ALMAU SYLLABUS
echo   (Ne zakryvay chernye okna!)
echo ===================================================

:: 1. Запускаем сервер сайта (Официант)
start "DJANGO SERVER (SITE)" cmd /k "venv312\Scripts\activate && python manage.py runserver"

:: 2. Запускаем ИИ Воркера (Повар)
start "AI WORKER (BRAINS)" cmd /k "venv312\Scripts\activate && python manage.py run_worker"

echo.
echo Vse zapusheno! Sayt dostupen po adresu: http://127.0.0.1:8000
echo.
timeout /t 10