@echo off
setlocal

set "SCRIPT=%USERPROFILE%\.codex\mcp_servers\antigravity_widget.py"
if not exist "%SCRIPT%" (
    if exist "D:\codex-antigravity-bridge\widget\antigravity_widget.py" (
        set "SCRIPT=D:\codex-antigravity-bridge\widget\antigravity_widget.py"
    )
)

:: 1. Try Python 3.11 absolute path
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
if exist "%PY%" (
    start "" "%PY%" "%SCRIPT%"
    exit /b 0
)

:: 2. Try pythonw in PATH
where pythonw.exe >nul 2>nul
if %ERRORLEVEL% equ 0 (
    start "" pythonw "%SCRIPT%"
    exit /b 0
)

:: 3. Fallback to python
where python.exe >nul 2>nul
if %ERRORLEVEL% equ 0 (
    start "" python "%SCRIPT%"
    exit /b 0
)

echo [ERROR] Python not found.
pause
exit /b 1
