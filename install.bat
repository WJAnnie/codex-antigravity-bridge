@echo off
chcp 65001 >nul
title 安装 Codex Antigravity Bridge

echo 正在通过 PowerShell 执行一键安装...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 安装过程中遇到错误，请检查上方日志。
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo 按任意键退出安装程序...
pause >nul
exit /b 0
