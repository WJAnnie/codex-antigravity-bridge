<#
.SYNOPSIS
    Codex Antigravity Bridge 一键安装脚本
.DESCRIPTION
    自动化部署 Antigravity MCP 服务、子智能体配置、桌面悬浮监控窗及快捷方式。
#>

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  🚀 Codex Antigravity Bridge 一键安装程序" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. 检查 Python
Write-Host "`n[1/6] 检查 Python 环境..." -ForegroundColor Yellow
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Error "❌ 未在 PATH 中找到 python 命令，请先安装 Python 3.10+。"
}
$pyVer = python --version
Write-Host "  ✔ 检测到: $pyVer" -ForegroundColor Green

# 2. 检查并安装核心 Python 依赖
Write-Host "`n[2/6] 检查核心依赖 (google-antigravity, mcp)..." -ForegroundColor Yellow
$deps = @("google-antigravity", "mcp")
foreach ($dep in $deps) {
    $check = python -c "import $($dep.Replace('-', '_'))" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ⬇ 正在安装依赖: $dep ..." -ForegroundColor Gray
        python -m pip install $dep --quiet
    } else {
        Write-Host "  ✔ $dep 已就绪" -ForegroundColor Green
    }
}

# 3. 创建目录结构
Write-Host "`n[3/6] 初始化 ~/.codex 目录结构..." -ForegroundColor Yellow
$homeDir = [Environment]::GetFolderPath("UserProfile")
$codexDir = Join-Path $homeDir ".codex"
$mcpDir = Join-Path $codexDir "mcp_servers"
$agentsDir = Join-Path $codexDir "agents"

New-Item -ItemType Directory -Force -Path $mcpDir | Out-Null
New-Item -ItemType Directory -Force -Path $agentsDir | Out-Null
Write-Host "  ✔ 目标目录已确认: $codexDir" -ForegroundColor Green

# 4. 拷贝核心组件
Write-Host "`n[4/6] 复制 MCP 服务与监控组件..." -ForegroundColor Yellow
$scriptRoot = $PSScriptRoot
if (-not $scriptRoot) { $scriptRoot = Get-Location }

$mcpSrc = Join-Path $scriptRoot "mcp_servers\antigravity_mcp.py"
$widgetSrc = Join-Path $scriptRoot "widget\antigravity_widget.py"
$agentSrc = Join-Path $scriptRoot "agents\antigravity.toml"
$launcherSrc = Join-Path $scriptRoot "launcher\启动Antigravity监控窗.bat"

Copy-Item -Path $mcpSrc -Destination (Join-Path $mcpDir "antigravity_mcp.py") -Force
Copy-Item -Path $widgetSrc -Destination (Join-Path $mcpDir "antigravity_widget.py") -Force
Copy-Item -Path $agentSrc -Destination (Join-Path $agentsDir "antigravity.toml") -Force
Write-Host "  ✔ antigravity_mcp.py -> $mcpDir" -ForegroundColor Green
Write-Host "  ✔ antigravity_widget.py -> $mcpDir" -ForegroundColor Green
Write-Host "  ✔ antigravity.toml -> $agentsDir" -ForegroundColor Green

# 5. 配置 ~/.codex/config.toml
Write-Host "`n[5/6] 校验 ~/.codex/config.toml MCP 配置..." -ForegroundColor Yellow
$configFile = Join-Path $codexDir "config.toml"
$pythonPath = (Get-Command python).Source.Replace("\", "/")
$targetScriptPath = (Join-Path $mcpDir "antigravity_mcp.py").Replace("\", "/")

$tomlBlock = @"

[mcp_servers.antigravity]
command = "python"
args = ["-u", "$targetScriptPath"]
"@

if (Test-Path $configFile) {
    $existingContent = Get-Content -Path $configFile -Raw -Encoding UTF8
    if ($existingContent -notmatch "\[mcp_servers\.antigravity\]") {
        Add-Content -Path $configFile -Value $tomlBlock -Encoding UTF8
        Write-Host "  ✔ 已将 [mcp_servers.antigravity] 注入 config.toml" -ForegroundColor Green
    } else {
        Write-Host "  ✔ config.toml 中已存在 antigravity 配置，无需重复添加" -ForegroundColor Green
    }
} else {
    Set-Content -Path $configFile -Value $tomlBlock.TrimStart() -Encoding UTF8
    Write-Host "  ✔ 已新建 config.toml 并写入配置" -ForegroundColor Green
}

# 6. 创建桌面快捷启动方式
Write-Host "`n[6/6] 创建桌面监控窗快捷方式..." -ForegroundColor Yellow
$desktopDir = [Environment]::GetFolderPath("Desktop")
$desktopBat = Join-Path $desktopDir "启动Antigravity监控窗.bat"
Copy-Item -Path $launcherSrc -Destination $desktopBat -Force
Write-Host "  ✔ 桌面快捷方式已生成: $desktopBat" -ForegroundColor Green

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  🎉 安装成功！Codex Antigravity Bridge 已就绪" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "💡 接下来你只需："
Write-Host "  1. 双击桌面的【启动Antigravity监控窗.bat】开启悬浮监控" -ForegroundColor Yellow
Write-Host "  2. 重启或打开 Codex，它将自动加载 antigravity MCP" -ForegroundColor Yellow
Write-Host "  3. 在对话中直接要求 Codex：'请委派 antigravity 审查此代码' 或使用 @antigravity" -ForegroundColor Yellow
Write-Host "==========================================================`n" -ForegroundColor Cyan
