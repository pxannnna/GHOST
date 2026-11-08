param([string]$IdfPath = '', [string]$ToolsPath = '', [string]$Source = '')
$ErrorActionPreference = 'Stop'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git for Windows first.' }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 and add it to PATH first.' }
$cache = Join-Path $PSScriptRoot '.cache'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
if (-not $IdfPath) {
    $IdfPath = Join-Path $cache 'esp-idf'
    if (-not (Test-Path -LiteralPath $IdfPath)) {
        & git clone --branch v5.5.4 --depth 1 --recursive https://github.com/espressif/esp-idf.git $IdfPath
        if ($LASTEXITCODE -ne 0) { throw 'ESP-IDF download failed.' }
    }
}
$IdfPath = (Resolve-Path -LiteralPath $IdfPath).Path
$tag = & git -C $IdfPath describe --tags --exact-match
if ($LASTEXITCODE -ne 0 -or $tag.Trim() -ne 'v5.5.4') { throw 'This demo requires exactly ESP-IDF v5.5.4.' }
if (-not $ToolsPath) { $ToolsPath = Join-Path $cache 'idf-tools' }
$env:IDF_TOOLS_PATH = [System.IO.Path]::GetFullPath($ToolsPath)
& (Join-Path $IdfPath 'install.ps1') esp32c6
if ($LASTEXITCODE -ne 0) { throw 'ESP-IDF tool installation failed.' }
. (Join-Path $IdfPath 'export.ps1')
if (-not $env:IDF_PATH) { throw 'ESP-IDF activation failed.' }
if ($Source) {
    & python (Join-Path $PSScriptRoot 'build.py') --source $Source
} else {
    & python (Join-Path $PSScriptRoot 'build.py')
}
if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed.' }
Write-Host 'Package built. Open the demo and click Install / update firmware.'
