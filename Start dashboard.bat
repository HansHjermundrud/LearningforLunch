@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 dashboard\server.py %*
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.10 or newer is required. Install Python, then run this launcher again.
  ) else (
    python dashboard\server.py %*
  )
)
pause
