# Builds the Windows onedir executable and a release zip.
#
# Usage (from anywhere):
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Python "C:\Path\To\python.exe" -Version 1.0.0
#
# Output: dist\DATAelectricWORKs\DATAelectricWORKs.exe
#         dist\DATAelectricWORKs-v<Version>-windows-x64.zip

param(
    [string]$Python = "python",
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Installing runtime and build dependencies..."
& $Python -m pip install --quiet "pandas==2.2.3" "numpy==2.1.3" streamlit plotly openpyxl xlrd xlwt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$work = Join-Path $root "build\pyinstaller"
$dist = Join-Path $root "dist"

Write-Host "Running PyInstaller..."
& $Python -m PyInstaller --noconfirm --onedir --console --name DATAelectricWORKs `
    --distpath $dist --workpath $work --specpath $work `
    --add-data "$(Join-Path $root 'app.py');." `
    --add-data "$(Join-Path $root 'data_handler.py');." `
    --add-data "$(Join-Path $root 'tou_analyzer.py');." `
    --hidden-import data_handler `
    --hidden-import tou_analyzer `
    --collect-all streamlit `
    --copy-metadata streamlit `
    --collect-data plotly `
    packaging\launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$zip = Join-Path $dist "DATAelectricWORKs-v$Version-windows-x64.zip"
Write-Host "Creating $zip ..."
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $dist "DATAelectricWORKs") -DestinationPath $zip

Write-Host "Done: $zip"
