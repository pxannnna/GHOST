param([switch]$Launch)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location -LiteralPath $repoRoot
$venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv (Join-Path $repoRoot '.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $repoRoot '.venv')
    } else {
        throw 'Install Python 3.12 from python.org (including Tcl/Tk), then run this launcher again.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the environment. Install Python 3.12 including Tcl/Tk.' }
}
& $venvPython -c "import sys,tkinter; assert sys.version_info[:2] == (3,12), 'Use Python 3.12 for this pinned environment'"
if ($LASTEXITCODE -ne 0) { throw 'Python or Tk is unavailable. Install Python 3.12 including Tcl/Tk.' }
$requirementsFile = Join-Path $PSScriptRoot 'requirements-demo.lock.txt'
$signature = (Get-FileHash -LiteralPath $requirementsFile -Algorithm SHA256).Hash
$marker = Join-Path $repoRoot '.venv/csi-demo-requirements.sha256'
$installedSignature = if (Test-Path -LiteralPath $marker) { (Get-Content -LiteralPath $marker -Raw).Trim() } else { '' }
if ($installedSignature -ne $signature) {
    & $venvPython -m pip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check Internet access and rerun.' }
    Set-Content -LiteralPath $marker -Value $signature
}
& $venvPython -c "import serial,esptool,matplotlib,tkinter; import services.wifi.demo.app"
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed. Delete only .venv/csi-demo-requirements.sha256 and rerun setup.' }
Write-Host 'GHOST CSI demo environment is ready.'
if ($Launch) {
    $logs = Join-Path $repoRoot 'data/wifi/demo'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    Start-Process -FilePath (Join-Path $repoRoot '.venv/Scripts/pythonw.exe') `
        -ArgumentList @('-m','services.wifi.demo') -WorkingDirectory $repoRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "app-$stamp.out.log") `
        -RedirectStandardError (Join-Path $logs "app-$stamp.err.log") | Out-Null
}
