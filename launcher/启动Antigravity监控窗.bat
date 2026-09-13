@echo off
chcp 65001 >nul
title Antigravity 监控窗启动器

:: 优先寻找 pythonw（后台无黑窗）
where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY=pythonw"
) else (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
    ) else (
        where python >nul 2>nul
        if %ERRORLEVEL% EQU 0 (
            set "PY=python"
        ) else (
            echo 未检测到 Python，请确保已安装 Python 并添加到环境变量。
            pause
            exit /b 1
        )
    )
)

:: 探测监控窗脚本路径
if exist "%USERPROFILE%\.codex\mcp_servers\antigravity_widget.py" (
    set "TARGET_SCRIPT=%USERPROFILE%\.codex\mcp_servers\antigravity_widget.py"
) else if exist "%~dp0..\widget\antigravity_widget.py" (
    set "TARGET_SCRIPT=%~dp0..\widget\antigravity_widget.py"
) else (
    echo 找不到 antigravity_widget.py 脚本！
    pause
    exit /b 1
)

start "" "%PY%" "%TARGET_SCRIPT%"
exit
