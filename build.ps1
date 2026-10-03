# Build Script for AI Keylogger Detection System
# Usage: .\build.ps1

param(
    [switch]$Clean,
    [switch]$Debug
)

$AppName = "KeyloggerDetector"
$SpecFile = "keylogger_detector.spec"

Write-Host ""
Write-Host "AI Keylogger Detection System - Build Script" -ForegroundColor Blue
Write-Host "=============================================" -ForegroundColor Blue
Write-Host ""

# Check Python
Write-Host "Checking Python..." -ForegroundColor Cyan
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "ERROR: Python not found" -ForegroundColor Red
    exit 1
}

# Check PyInstaller
Write-Host "Checking PyInstaller..." -ForegroundColor Cyan
$pyinstallerVersion = python -m PyInstaller --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: PyInstaller $pyinstallerVersion" -ForegroundColor Green
} else {
    Write-Host "WARNING: PyInstaller not found, installing..." -ForegroundColor Yellow
    pip install pyinstaller
}

# Clean
if ($Clean) {
    Write-Host ""
    Write-Host "Cleaning previous builds..." -ForegroundColor Cyan
    if (Test-Path "dist") {
        Remove-Item "dist" -Recurse -Force
        Write-Host "Removed dist/" -ForegroundColor Green
    }
    if (Test-Path "build") {
        Remove-Item "build" -Recurse -Force
        Write-Host "Removed build/" -ForegroundColor Green
    }
}

# Check icon
Write-Host ""
Write-Host "Checking icon..." -ForegroundColor Cyan
if (Test-Path "icon.ico") {
    Write-Host "OK: icon.ico exists" -ForegroundColor Green
} else {
    Write-Host "Generating icon..." -ForegroundColor Yellow
    python create_icon.py
}

# Debug mode
if ($Debug) {
    Write-Host ""
    Write-Host "DEBUG MODE: Enabling console window" -ForegroundColor Yellow
    if (Test-Path $SpecFile) {
        Copy-Item $SpecFile "$SpecFile.bak" -Force
        $content = Get-Content $SpecFile -Raw
        $content = $content -replace "console=False", "console=True"
        Set-Content $SpecFile $content -NoNewline
    }
}

# Build
Write-Host ""
Write-Host "Building executable..." -ForegroundColor Cyan
Write-Host ""
python -m PyInstaller $SpecFile --clean

# Restore spec
if ($Debug -and (Test-Path "$SpecFile.bak")) {
    Move-Item "$SpecFile.bak" $SpecFile -Force
}

# Check result
Write-Host ""
if (Test-Path "dist\$AppName.exe") {
    $fileSize = [math]::Round((Get-Item "dist\$AppName.exe").Length / 1MB, 2)
    Write-Host "=============================================" -ForegroundColor Green
    Write-Host "BUILD SUCCESSFUL!" -ForegroundColor Green
    Write-Host "=============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Output: dist\$AppName.exe" -ForegroundColor Cyan
    Write-Host "Size:   $fileSize MB" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Test it: .\dist\$AppName.exe" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "=============================================" -ForegroundColor Red
    Write-Host "BUILD FAILED!" -ForegroundColor Red
    Write-Host "=============================================" -ForegroundColor Red
    exit 1
}
