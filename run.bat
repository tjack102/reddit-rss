@echo off
cd /d "%~dp0"
echo Running RSS Feed Digest...
python run_digest.py
echo.
echo Process complete.
pause
