$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPythonw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"

if (-not (Test-Path -LiteralPath $VenvPythonw)) {
    throw "尚未安装项目环境，请先运行 setup.ps1。"
}

Start-Process -FilePath $VenvPythonw -ArgumentList @((Join-Path $ProjectDir "signal_monitor_gui.py")) -WorkingDirectory $ProjectDir
