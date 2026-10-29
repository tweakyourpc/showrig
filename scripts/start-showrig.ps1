param([Parameter(ValueFromRemainingArguments = $true)][string[]]$ShowrigArguments)
$ErrorActionPreference = 'Stop'
$ShowrigSource = Split-Path $PSScriptRoot -Parent
$ShowrigPython = Join-Path $ShowrigSource '.venv/Scripts/python.exe'
if (-not (Test-Path $ShowrigPython)) {
    throw 'Run ./scripts/setup.ps1 first. Starting Showrig never installs or downloads prerequisites.'
}
Set-Location $ShowrigSource
& $ShowrigPython -m showrig web --projects (Join-Path $ShowrigSource 'films') @ShowrigArguments
exit $LASTEXITCODE
