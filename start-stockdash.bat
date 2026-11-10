@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 launch.py
    goto :done
)
where python >nul 2>nul
if not errorlevel 1 (
    python launch.py
    goto :done
)
echo Python was not found. Install Python 3.9 or newer from python.org
pause
exit /b 1
:done
if errorlevel 1 pause
