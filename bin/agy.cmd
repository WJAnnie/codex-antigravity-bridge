@echo off
setlocal
set "CLI_SCRIPT=%~dp0..\..\..\.codex\mcp_servers\antigravity_cli.py"
if not exist "%CLI_SCRIPT%" (
    if exist "%USERPROFILE%\.codex\mcp_servers\antigravity_cli.py" (
        set "CLI_SCRIPT=%USERPROFILE%\.codex\mcp_servers\antigravity_cli.py"
    ) else if exist "C:\Users\Darli\.codex\mcp_servers\antigravity_cli.py" (
        set "CLI_SCRIPT=C:\Users\Darli\.codex\mcp_servers\antigravity_cli.py"
    )
)
python "%CLI_SCRIPT%" %*
exit /b %ERRORLEVEL%
