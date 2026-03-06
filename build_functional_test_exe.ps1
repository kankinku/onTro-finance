Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildVenv = Join-Path $env:TEMP "ontro-finance-build-venv"
$VenvPython = Join-Path $BuildVenv "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    py -3 -m venv $BuildVenv
}

Push-Location $ScriptDir
try {
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r requirements.txt
    & $VenvPython -m pip install pyinstaller

    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --name onTroFinanceFunctionalTest `
        --collect-submodules src `
        --collect-submodules tests `
        --collect-submodules config `
        --add-data ".env.example;." `
        --add-data "README.md;." `
        --add-data "config;config" `
        --add-data "data;data" `
        --add-data "docs;docs" `
        --add-data "tests;tests" `
        functional_test_runner.py
}
finally {
    Pop-Location
}
