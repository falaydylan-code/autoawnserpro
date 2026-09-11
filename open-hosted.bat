@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe hosted_access.py
if errorlevel 1 pause
