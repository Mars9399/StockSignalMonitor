$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$OutputDir = Join-Path $ProjectDir "build-output"
$WorkDir = Join-Path $ProjectDir "build-temp"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "尚未安装项目环境，请先运行 setup.ps1。"
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name StockSignalMonitor `
    --distpath $OutputDir `
    --workpath $WorkDir `
    --specpath $WorkDir `
    --collect-all alpaca `
    --collect-all yfinance `
    --collect-all polygon `
    --collect-all ibapi `
    --hidden-import signal_monitor `
    --hidden-import data_providers `
    --hidden-import tws_positions `
    (Join-Path $ProjectDir "signal_monitor_gui.py")

if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败。" }

Copy-Item -LiteralPath (Join-Path $ProjectDir ".env.example") -Destination (Join-Path $OutputDir "StockSignalMonitor\.env.example") -Force
Copy-Item -LiteralPath (Join-Path $ProjectDir "docs\部署说明.txt") -Destination (Join-Path $OutputDir "StockSignalMonitor\部署说明.txt") -Force
Write-Host "构建完成：$OutputDir"
