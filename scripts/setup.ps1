param([switch]$Voices)
$ErrorActionPreference = 'Stop'
$ShowrigSource = Split-Path $PSScriptRoot -Parent
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m venv (Join-Path $ShowrigSource '.venv')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m venv (Join-Path $ShowrigSource '.venv')
} else {
    throw 'Install Python 3.11 or newer, then run this script again.'
}
if ($LASTEXITCODE -ne 0) { throw 'Could not create the Showrig Python environment.' }
$ShowrigPython = Join-Path $ShowrigSource '.venv/Scripts/python.exe'
$ShowrigWheels = Join-Path $ShowrigSource 'runtime/wheels'
if (Test-Path $ShowrigWheels) {
    & $ShowrigPython -m pip install --no-index --find-links $ShowrigWheels $ShowrigSource
} else {
    Write-Host 'Installing Showrig Python dependencies. This setup step needs a connection.'
    & $ShowrigPython -m pip install $ShowrigSource
}
if ($LASTEXITCODE -ne 0) { throw 'Showrig installation did not finish.' }
if ($Voices) {
    & $ShowrigPython -m showrig setup --install-voices
    if ($LASTEXITCODE -ne 0) { throw 'Optional voice setup did not finish.' }
}
Write-Host 'Showrig installed. Add native tools using Setup & extras, then run ./scripts/start-showrig.ps1.'
