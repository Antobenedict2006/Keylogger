# ============================================================================
# Build Script for AI Keylogger Detection System
# ============================================================================
# This script automates the process of building the standalone Windows .exe
#
# Usage:
#   .\build.ps1                    # Build with default options
#   .\build.ps1 -Clean             # Clean build (removes cache)
#   .\build.ps1 -SkipTests         # Build without running tests
#
# Requirements:
#   - Python 3.8+
#   - PyInstaller (pip install pyinstaller)
#   - All dependencies from requirements.txt
# ============================================================================

param(
    [switch]$Clean,
    [switch]$SkipTests,
    [switch]$Verbose
)

# Configuration
$AppName = "KeyloggerDetector"
$Version = "1.0.0"
$IconFile = "icon.ico"
$SpecFile = "keylogger_detector.spec"

# Colors for output
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Failure { Write-Host $args -ForegroundColor Red }

# Banner
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║     AI Keylogger Detection System - Build Script v$Version     ║" -ForegroundColor Blue
Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

# Check Python installation
Write-Info "Checking Python installation..."
try {
    $pythonVersion = python --version 2>&1
    Write-Success "✓ $pythonVersion"
} catch {
    Write-Failure "✗ Python not found. Please install Python 3.8 or higher."
    exit 1
}

# Check PyInstaller
Write-Info "Checking PyInstaller..."
try {
    $pyinstallerVersion = pyinstaller --version 2>&1
    Write-Success "✓ PyInstaller $pyinstallerVersion"
} catch {
    Write-Warning "✗ PyInstaller not found. Installing..."
    pip install pyinstaller
}

# Clean previous builds
if ($Clean) {
    Write-Info "Cleaning previous builds..."
    if (Test-Path "dist") { 
        Remove-Item "dist" -Recurse -Force
        Write-Success "✓ Removed dist/"
    }
    if (Test-Path "build") { 
        Remove-Item "build" -Recurse -Force
        Write-Success "✓ Removed build/"
    }
    if (Test-Path "$AppName.spec") {
        Remove-Item "$AppName.spec" -Force
        Write-Success "✓ Removed old spec file"
    }
}

# Create icon if missing
Write-Info "Checking application icon..."
if (-Not (Test-Path $IconFile)) {
    Write-Warning "✗ Icon not found. Generating..."
    python create_icon.py
    if (Test-Path $IconFile) {
        Write-Success "✓ Icon created successfully"
    } else {
        Write-Warning "! Icon creation failed, continuing without icon..."
    }
} else {
    Write-Success "✓ Icon found"
}

# Check if ML model exists
Write-Info "Checking ML model..."
if (Test-Path "models\keylogger_detector.joblib") {
    Write-Success "✓ ML model found"
} else {
    Write-Warning "! ML model not found. The application will use heuristic mode."
    Write-Warning "  To train a model, run: python tools\train_model.py"
}

# Run tests (optional)
if (-Not $SkipTests) {
    Write-Info "Running pre-build checks..."
    try {
        python -m src.ui.dashboard
        Write-Success "✓ Import checks passed"
    } catch {
        Write-Warning "! Import warnings detected (may be OK)"
    }
}

# Build with PyInstaller
Write-Info "Building executable..."
Write-Host ""

if ($Verbose) {
    pyinstaller $SpecFile --clean --log-level DEBUG
} else {
    pyinstaller $SpecFile --clean
}

# Check build result
Write-Host ""
if (Test-Path "dist\$AppName.exe") {
    Write-Success "════════════════════════════════════════════════════════════════"
    Write-Success "  BUILD SUCCESSFUL!"
    Write-Success "════════════════════════════════════════════════════════════════"
    Write-Host ""
    
    # Show file information
    $exePath = "dist\$AppName.exe"
    $fileSize = (Get-Item $exePath).Length / 1MB
    $fileSizeMB = [math]::Round($fileSize, 2)
    
    Write-Info "Output file:  $exePath"
    Write-Info "File size:    $fileSizeMB MB"
    Write-Info "Version:      $Version"
    Write-Host ""
    
    # Check if UPX was used
    if ($fileSizeMB -lt 70) {
        Write-Success "✓ File size optimized (UPX compression detected)"
    } else {
        Write-Warning "! Large file size. Consider installing UPX for compression:"
        Write-Warning "  Download from: https://github.com/upx/upx/releases"
    }
    
    Write-Host ""
    Write-Info "Next steps:"
    Write-Host "  1. Test the executable: .\dist\$AppName.exe" -ForegroundColor White
    Write-Host "  2. Test command line:   .\dist\$AppName.exe --help" -ForegroundColor White
    Write-Host "  3. Test on clean PC:    Copy to a machine without Python" -ForegroundColor White
    Write-Host ""
    
    # Offer to run the application
    $runNow = Read-Host "Run the application now? (y/n)"
    if ($runNow -eq "y" -or $runNow -eq "Y") {
        Write-Info "Starting $AppName..."
        Start-Process "dist\$AppName.exe"
    }
    
} else {
    Write-Failure "════════════════════════════════════════════════════════════════"
    Write-Failure "  BUILD FAILED!"
    Write-Failure "════════════════════════════════════════════════════════════════"
    Write-Host ""
    Write-Warning "Check the build log above for errors."
    Write-Warning "Common issues:"
    Write-Host "  • Missing dependencies: pip install -r requirements.txt" -ForegroundColor White
    Write-Host "  • Import errors: Check Python path and module structure" -ForegroundColor White
    Write-Host "  • Spec file errors: Review $SpecFile configuration" -ForegroundColor White
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Success "Build script completed."
