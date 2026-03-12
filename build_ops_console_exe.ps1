Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildVenv = Join-Path $env:TEMP "ontro-finance-ops-build-venv"
$VenvPython = Join-Path $BuildVenv "Scripts\python.exe"
$SupportedPython = @("3.11", "3.12")

function Get-PythonMinorVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )

    & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
}

if (Test-Path $VenvPython) {
    $ExistingVersion = Get-PythonMinorVersion -PythonExe $VenvPython
    if ($SupportedPython -notcontains $ExistingVersion) {
        Remove-Item -Recurse -Force $BuildVenv
    }
}

if (-not (Test-Path $VenvPython)) {
    py -3.11 -m venv $BuildVenv
}

$BuildPythonVersion = Get-PythonMinorVersion -PythonExe $VenvPython
if ($SupportedPython -notcontains $BuildPythonVersion) {
    throw "Unsupported Python runtime for build venv: $BuildPythonVersion. Install Python 3.11 or 3.12 and rerun."
}

Push-Location $ScriptDir
try {
    Push-Location frontend
    try {
        npm ci
        npm run build
    }
    finally {
        Pop-Location
    }

    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r requirements.txt
    & $VenvPython -m pip install pyinstaller

    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        onTroFinanceStarter.spec
}
finally {
    Pop-Location
}
