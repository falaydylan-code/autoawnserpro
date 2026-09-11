@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto fail
if not exist .env copy .env.example .env >nul
echo Ready. Double-click start.bat, then open http://127.0.0.1:8010
pause
exit /b 0
:fail
echo Setup did not finish. Check that Python and an internet connection are available, then try again.
pause
exit /b 1
