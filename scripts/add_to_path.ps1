$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "Error: This script requires administrator privileges" -ForegroundColor Red
    exit 1
}

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = (Resolve-Path $scriptsDir).Path
Write-Host "Adding scripts directory to PATH: $scriptsDir" -ForegroundColor Green

$currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
if ($currentPath -like "*$scriptsDir*") {
    Write-Host "Already in PATH" -ForegroundColor Green
    exit 0
}

$newPath = "$scriptsDir;$currentPath"
[Environment]::SetEnvironmentVariable("PATH", $newPath, "Machine")
Write-Host "Successfully added to PATH" -ForegroundColor Green
Write-Host "Please restart your terminal" -ForegroundColor Yellow
