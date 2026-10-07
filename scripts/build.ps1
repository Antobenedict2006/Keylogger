# Build Script for AI Keylogger Detection System
# Updated for organized project structure
# Usage: .\scripts\build.ps1 -Clean

param(
    [switch]$Clean
)

$AppName = "KeyloggerDetector"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SpecFile = Join-Path $ProjectRoot "config\keylogger_detector.spec"
$IconFile = Join-Path $ProjectRoot "assets\icon.ico"
$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build"

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
    if (Test-Path $DistDir) {
        Remove-Item $DistDir -Recurse -Force
        Write-Host "Removed dist/" -ForegroundColor Green
    }
    if (Test-Path $BuildDir) {
        Remove-Item $BuildDir -Recurse -Force
        Write-Host "Removed build/" -ForegroundColor Green
    }
}

# Check icon
Write-Host ""
Write-Host "Checking icon..." -ForegroundColor Cyan
if (Test-Path $IconFile) {
    Write-Host "OK: icon.ico exists" -ForegroundColor Green
} else {
    Write-Host "ERROR: Icon file not found at $IconFile" -ForegroundColor Red
    exit 1
}

# Build
Write-Host ""
Write-Host "Building executable..." -ForegroundColor Cyan
Write-Host ""

# Change to project root directory for build
Set-Location $ProjectRoot

# Run PyInstaller
python -m PyInstaller $SpecFile --noconfirm

# Check result
$ExePath = Join-Path $DistDir "$AppName.exe"
if (Test-Path $ExePath) {
    $FileSize = (Get-Item $ExePath).Length
    $FileSizeMB = [math]::Round($FileSize / 1MB, 2)
    $BuildTime = (Get-Item $ExePath).LastWriteTime

    Write-Host ""
    Write-Host "=============================================" -ForegroundColor Blue
    Write-Host "BUILD SUCCESSFUL!" -ForegroundColor Green
    Write-Host "=============================================" -ForegroundColor Blue
    Write-Host "Output: dist\$AppName.exe" -ForegroundColor Green
    Write-Host "Size:   $FileSizeMB MB" -ForegroundColor Green
    Write-Host "Time:   $BuildTime" -ForegroundColor Green
    Write-Host ""
    Write-Host "Test it: .\dist\$AppName.exe" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "BUILD FAILED!" -ForegroundColor Red
    Write-Host "Check the output above for errors." -ForegroundColor Red
    exit 1
}
