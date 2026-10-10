# Installer Build Guide

## Prerequisites

This installer requires **Inno Setup** to compile. If you haven't installed it yet:

1. Download from: https://jrsoftware.org/isdl.php
2. Run the installer (use default settings)
3. Standard installation path: `C:\Program Files (x86)\Inno Setup 6\`

## Building the Installer

### Option 1: Automated Build (Recommended)

Simply run:
```powershell
.\installer\build_installer.ps1
```

This script will:
- ✅ Verify `dist\KeyloggerDetector.exe` exists
- ✅ Auto-detect Inno Setup installation
- ✅ Compile the installer
- ✅ Report size and location

### Option 2: Manual Build

If you prefer to compile manually:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\KeyloggerDetector.iss
```

## Output

After successful compilation:
- **Location:** `installer_output\KeyloggerDetector_Setup.exe`
- **Size:** ~80-85 MB (LZMA compressed)
- **Contains:** The full KeyloggerDetector.exe application

## Installer Features

The compiled installer includes:

### Installation Options
- ✅ Modern wizard interface
- ✅ License terms display (LICENSE.txt)
- ✅ Installs to `Program Files\KeyloggerDetector`
- ✅ Requires administrator privileges
- ✅ Optional desktop shortcut (unchecked by default)
- ✅ Start menu shortcuts
- ✅ Uninstaller

### What Users Will See
1. **Welcome screen** with app version
2. **License agreement** (must accept to continue)
3. **Installation directory** selection
4. **Desktop shortcut** option
5. **Installation progress**
6. **Completion** with optional "Launch now"

## Files Included

- `KeyloggerDetector.iss` - Inno Setup script
- `LICENSE.txt` - Terms of use and data disclosure
- `build_installer.ps1` - Automated build script

## Troubleshooting

### "dist\KeyloggerDetector.exe not found"
Run `build.ps1` first to create the executable:
```powershell
.\build.ps1
```

### "Inno Setup not found"
Install from https://jrsoftware.org/isdl.php and try again.

### "Access denied" during compilation
Run PowerShell as Administrator.

## Distribution

After building, you can distribute `KeyloggerDetector_Setup.exe` to users.

**Installer size:** The 80MB exe is compressed to ~80MB (LZMA is already very efficient with PyInstaller bundles).

**User requirements:**
- Windows 10/11 (64-bit)
- Administrator rights for installation
- No Python installation needed (fully bundled)
