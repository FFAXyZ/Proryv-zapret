@echo off
chcp 6501 >nul
title ПРОРЫВ — запуск
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo [x] Python не найден. Установите Python 3.10+ с https://www.python.org/downloads/
  pause
  exit /b 1
)
echo [*] Установка зависимостей...
pip install -r requirements.txt
echo [*] Запуск ПРОРЫВ...
python -m app.main
pause
