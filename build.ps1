$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "src"

python -m pip install --upgrade pyinstaller
python -m unittest discover -s tests -v
python -m PyInstaller --noconfirm --clean "rvb_vault.spec"

Write-Host "Build complete: $projectRoot\dist\RVB Vault\RVB Vault.exe"
