# Building Standalone Executable (.exe)

This guide explains how to convert the AI Keylogger Detection System into a standalone Windows executable.

---

## Prerequisites

### 1. Install PyInstaller

```powershell
pip install pyinstaller
```

### 2. Install UPX (Optional, for smaller file size)

UPX compresses the executable, reducing size by ~30%.

1. Download UPX from: https://github.com/upx/upx/releases
2. Extract `upx.exe` to a folder (e.g., `C:\Tools\upx`)
3. Add that folder to your system PATH

To test if UPX is installed:
```powershell
upx --version
```

### 3. Create Application Icon

An icon file (`icon.ico`) is required. You can:

**Option A: Use the included icon generator script:**
```powershell
python create_icon.py
```

**Option B: Create manually:**
1. Use an online converter (e.g., https://convertio.co/png-ico/)
2. Convert a 256x256 PNG image to `.ico` format
3. Save as `icon.ico` in the project root

---

## Building the Executable

### Method 1: Using the Spec File (Recommended)

The `keylogger_detector.spec` file contains all configuration.

```powershell
# Build the executable
pyinstaller keylogger_detector.spec

# Output location:
# dist/KeyloggerDetector.exe
```

### Method 2: Command Line (Alternative)

If you prefer not to use the spec file:

```powershell
pyinstaller --onefile `
  --windowed `
  --name KeyloggerDetector `
  --icon icon.ico `
  --add-data "models/keylogger_detector.joblib;models" `
  --hidden-import sklearn.ensemble `
  --hidden-import sklearn.tree `
  --hidden-import sklearn.neighbors `
  --hidden-import tkinter `
  --hidden-import pystray `
  --hidden-import PIL `
  --exclude-module matplotlib `
  --exclude-module scipy `
  main.py
```

---

## Build Options Explained

| Option | Description |
|--------|-------------|
| `--onefile` | Creates a single executable (no folder of dependencies) |
| `--windowed` | No console window (GUI only mode) |
| `--name` | Output executable name |
| `--icon` | Application icon (.ico file) |
| `--add-data` | Include data files (e.g., ML model) |
| `--hidden-import` | Import modules not detected automatically |
| `--exclude-module` | Exclude unused modules (reduces size) |
| `--upx-dir` | Path to UPX if not in PATH |

---

## Output Files

After building:

```
dist/
├── KeyloggerDetector.exe    (50-80 MB single file)
```

The executable is **standalone** and includes:
- ✅ Python interpreter
- ✅ All Python dependencies (sklearn, psutil, tkinter, etc.)
- ✅ ML model file
- ✅ SQLite database support

---

## Running the Executable

### First Run

1. Double-click `KeyloggerDetector.exe`
2. Windows Defender may show a warning (unsigned executable)
3. Click "More info" → "Run anyway"

### Command Line Options

The executable supports the same options as `main.py`:

```powershell
# Headless mode (no GUI)
KeyloggerDetector.exe --no-gui

# Custom scan interval
KeyloggerDetector.exe --scan-interval 10

# Custom database path
KeyloggerDetector.exe --db C:\Logs\detections.db

# Show all options
KeyloggerDetector.exe --help
```

---

## Troubleshooting

### Issue: "Failed to execute script"

**Cause:** Missing dependencies or data files

**Fix:**
1. Add missing modules to `hidden_imports` in the spec file
2. Rebuild with: `pyinstaller keylogger_detector.spec --clean`

### Issue: "sklearn model failed to load"

**Cause:** ML model file not included

**Fix:**
1. Ensure `models/keylogger_detector.joblib` exists
2. Check `datas` section in spec file:
   ```python
   datas = [
       ('models/keylogger_detector.joblib', 'models'),
   ]
   ```
3. Rebuild

### Issue: Executable is too large (>100 MB)

**Solutions:**
1. Install and enable UPX compression (reduces by ~30%)
2. Exclude unused modules in spec file:
   ```python
   excludes=['matplotlib', 'scipy', 'IPython', 'jupyter']
   ```
3. Use `--onefile` mode (creates single file instead of folder)

### Issue: Antivirus flags the .exe as malicious

**Cause:** PyInstaller executables can trigger false positives

**Solutions:**
1. **Whitelist the file** in your antivirus
2. **Code sign** the executable (requires certificate, ~$200/year)
3. **Distribute source code** instead for technical users
4. Submit to antivirus vendors for whitelisting

### Issue: Application icon not showing

**Fix:**
1. Ensure `icon.ico` exists in project root
2. Verify icon path in spec file: `icon='icon.ico'`
3. Clear icon cache (Windows):
   ```powershell
   ie4uinit.exe -show
   ```

---

## Creating a Distributable Package

### Option 1: ZIP Archive

```powershell
# Create distribution folder
New-Item -ItemType Directory -Path "KeyloggerDetector_v1.0"

# Copy files
Copy-Item dist\KeyloggerDetector.exe KeyloggerDetector_v1.0\
Copy-Item README.md KeyloggerDetector_v1.0\
Copy-Item LICENSE KeyloggerDetector_v1.0\  # If you have one

# Create ZIP
Compress-Archive -Path KeyloggerDetector_v1.0 -DestinationPath KeyloggerDetector_v1.0_Windows.zip
```

### Option 2: Installer (Advanced)

Use tools like:
- **Inno Setup** (free, recommended): https://jrsoftware.org/isinfo.php
- **NSIS** (free): https://nsis.sourceforge.io/
- **InstallForge** (free): https://installforge.net/

---

## Testing Checklist

Before distributing the executable:

- [ ] Runs on a **clean Windows 10/11** machine (no Python installed)
- [ ] GUI launches correctly
- [ ] System tray icon appears
- [ ] Process monitoring works
- [ ] ML model loads successfully
- [ ] Database creates correctly
- [ ] Alerts appear for detected threats
- [ ] Application closes cleanly
- [ ] Command-line options work (`--help`, `--no-gui`, etc.)

---

## File Size Expectations

| Configuration | Size |
|--------------|------|
| No UPX | 80-100 MB |
| With UPX | 50-70 MB |
| With UPX + excludes | 40-60 MB |

---

## Security Considerations

### Code Signing (Recommended for Distribution)

1. Purchase a code signing certificate
2. Sign the executable:
   ```powershell
   signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com KeyloggerDetector.exe
   ```

Benefits:
- ✅ No Windows SmartScreen warnings
- ✅ Trusted by antivirus software
- ✅ Professional appearance

### Alternative: Self-Signing (For Testing Only)

```powershell
# Create self-signed certificate
New-SelfSignedCertificate -DnsName "KeyloggerDetector" -Type CodeSigning -CertStoreLocation Cert:\CurrentUser\My

# Export and sign
# (Not trusted by Windows, only for internal testing)
```

---

## Build Automation Script

Save as `build.ps1`:

```powershell
# Build script for Keylogger Detector
Write-Host "Building Keylogger Detector..." -ForegroundColor Green

# Clean previous builds
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (Test-Path build) { Remove-Item build -Recurse -Force }

# Create icon if missing
if (-Not (Test-Path icon.ico)) {
    Write-Host "Creating icon..." -ForegroundColor Yellow
    python create_icon.py
}

# Build with PyInstaller
Write-Host "Running PyInstaller..." -ForegroundColor Yellow
pyinstaller keylogger_detector.spec --clean

# Check if successful
if (Test-Path dist\KeyloggerDetector.exe) {
    Write-Host "✓ Build successful!" -ForegroundColor Green
    Write-Host "Output: dist\KeyloggerDetector.exe" -ForegroundColor Cyan
    
    # Show file size
    $size = (Get-Item dist\KeyloggerDetector.exe).Length / 1MB
    Write-Host "File size: $([math]::Round($size, 2)) MB" -ForegroundColor Cyan
} else {
    Write-Host "✗ Build failed!" -ForegroundColor Red
    exit 1
}
```

Run with:
```powershell
.\build.ps1
```

---

## Additional Resources

- **PyInstaller Documentation**: https://pyinstaller.org/
- **UPX Compressor**: https://upx.github.io/
- **Windows Code Signing**: https://learn.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools
- **Inno Setup**: https://jrsoftware.org/isinfo.php

---

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review PyInstaller logs in `build/KeyloggerDetector/`
3. Open an issue on GitHub with error details
