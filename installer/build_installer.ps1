# Build Installer Script for AI Keylogger Detection System
# Automatically locates Inno Setup and compiles the installer

Write-Host "=== AI Keylogger Detection System - Installer Builder ===" -ForegroundColor Cyan
Write-Host ""

# Check if dist\KeyloggerDetector.exe exists
if (-not (Test-Path "dist\KeyloggerDetector.exe")) {
    Write-Host "ERROR: dist\KeyloggerDetector.exe not found!" -ForegroundColor Red
    Write-Host "Please run build.ps1 first to create the executable." -ForegroundColor Yellow
    exit 1
}

# Locate Inno Setup Compiler
$isccPaths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    "C:\Program Files\Inno Setup 5\ISCC.exe",
    "C:\Users\Anto\Inno Setup 6\ISCC.exe"
)

$isccPath = $null
foreach ($path in $isccPaths) {
    if (Test-Path $path) {
        $isccPath = $path
        break
    }
}

if (-not $isccPath) {
    Write-Host "ERROR: Inno Setup not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Inno Setup from:" -ForegroundColor Yellow
    Write-Host "https://jrsoftware.org/isdl.php" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Searched locations:" -ForegroundColor Gray
    foreach ($path in $isccPaths) {
        Write-Host "  - $path" -ForegroundColor Gray
    }
    exit 1
}

Write-Host "Found Inno Setup: $isccPath" -ForegroundColor Green
Write-Host ""

# Create output directory
if (-not (Test-Path "installer_output")) {
    New-Item -ItemType Directory -Path "installer_output" | Out-Null
}

# Compile installer
Write-Host "Compiling installer..." -ForegroundColor Cyan
Write-Host ""

& $isccPath "installer\KeyloggerDetector.iss"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=== BUILD SUCCESSFUL ===" -ForegroundColor Green
    Write-Host ""
    
    $installerPath = "installer_output\KeyloggerDetector_Setup.exe"
    if (Test-Path $installerPath) {
        $size = (Get-Item $installerPath).Length / 1MB
        Write-Host "Installer created: $installerPath" -ForegroundColor Cyan
        Write-Host "Size: $([math]::Round($size, 2)) MB" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "You can now distribute this installer file." -ForegroundColor Green
    }
} else {
    Write-Host ""
    Write-Host "=== BUILD FAILED ===" -ForegroundColor Red
    Write-Host "Check the error messages above." -ForegroundColor Yellow
    exit 1
}
