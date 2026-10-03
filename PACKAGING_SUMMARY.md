# Packaging Summary - Quick Reference

This is a quick-reference guide to the packaging architecture for developers and maintainers.

---

## Architecture Overview

### Path Resolution Strategy

**Development Mode:**
```
Project Root/
  ├── models/             ← Models stored here
  ├── logs/               ← DB and logs here
  ├── data/               ← Whitelist, baselines here
  └── quarantine/         ← Quarantined files here
```

**Production (Frozen EXE):**
```
C:\Users\<User>\AppData\Local\Temp\_MEI<random>\     ← Temporary runtime files
                                                      (wiped on exit)

%LOCALAPPDATA%\KeyloggerDetector\                     ← Persistent user data
  ├── models/
  │   ├── keylogger_detector.joblib
  │   └── keylogger_detector_personalized.joblib
  ├── logs/
  │   ├── detector.log
  │   └── keylogger_events.db
  ├── data/
  │   ├── whitelist.json
  │   ├── typing_baseline.json
  │   └── mouse_baseline.json
  └── quarantine/
      └── <suspicious_exe>_<pid>_<timestamp>.quarantined
```

### Key Modules

| Module | Purpose | Key Function |
|--------|---------|--------------|
| `src/paths.py` | Centralized path resolution | `get_data_path()`, `is_frozen()` |
| `keylogger_detector.spec` | PyInstaller build config | Defines bundled data, imports, exclusions |
| `build.ps1` | Automated build script | Validates, cleans, builds, packages |
| `main.py` | Entry point | `multiprocessing.freeze_support()`, mutex |

---

## Critical Implementation Details

### 1. Path Resolution (src/paths.py)

```python
def is_frozen() -> bool:
    """Detect if running as PyInstaller exe."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

def get_user_data_root() -> Path:
    """
    Returns:
      - Frozen: %LOCALAPPDATA%\KeyloggerDetector
      - Dev:    <project_root>
    """
    if is_frozen():
        return Path.home() / "AppData" / "Local" / "KeyloggerDetector"
    return Path(__file__).parent.parent.resolve()
```

### 2. Single-Instance Enforcement (main.py)

```python
mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 
    "Global\\KeyloggerDetector_SingleInstance_Mutex")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    # Show message and exit
```

### 3. Multiprocessing Support (main.py)

```python
def main():
    multiprocessing.freeze_support()  # Must be first line
    # ...
```

### 4. PyInstaller Spec File

**Critical sections:**

```python
datas=[
    ('models/*.joblib', 'models'),        # Bundle models (optional)
    ('data/typing_baseline.json', 'data'), # Bundle baselines
]

hiddenimports=[
    'sklearn', 'psutil', 'tkinter', 'pynput', 'flask',
    'src.monitor', 'src.classifier', 'src.alert_manager',
    'src.db_logger', 'src.behavioral_analyzer', 'src.paths',
]

excludes=[
    'matplotlib', 'scipy', 'pandas',  # Reduce size
]

console=False,    # Windowed mode
icon='icon.ico',
upx=True,         # Enable compression
```

---

## Build Pipeline

### Automated Build (build.ps1)

```powershell
.\build.ps1           # Full clean build
.\build.ps1 -Debug    # Console mode for debugging
```

**Steps:**
1. Validate Python and PyInstaller
2. Clean `dist/` and `build/`
3. Generate `icon.ico` if missing
4. Run `pyinstaller keylogger_detector.spec --clean`
5. Copy optional files to `dist/`
6. Output: `dist\KeyloggerDetector.exe`

### Manual Build

```powershell
pyinstaller keylogger_detector.spec --clean
```

---

## Testing Checklist

### Pre-Build Tests

```powershell
# Test imports
python -c "from src.paths import get_data_path; print(get_data_path('logs', 'test.db'))"

# Test main application
python main.py --help
```

### Post-Build Tests

```powershell
# Basic launch
.\dist\KeyloggerDetector.exe

# Command-line options
.\dist\KeyloggerDetector.exe --help
.\dist\KeyloggerDetector.exe --minimized
.\dist\KeyloggerDetector.exe --no-gui

# Check data persistence
dir $env:LOCALAPPDATA\KeyloggerDetector

# Check logs
notepad $env:LOCALAPPDATA\KeyloggerDetector\logs\detector.log
```

### Single-Instance Test

1. Launch `KeyloggerDetector.exe`
2. Try launching again → Should show error message

### Clean-Machine Test

Test on a Windows machine **without Python installed**:
- Copy `KeyloggerDetector.exe` to target machine
- Double-click to run
- Verify all features work

---

## Common Issues & Solutions

### Issue: "Module not found" at runtime

**Cause:** PyInstaller missed a hidden import.

**Solution:** Add to `hiddenimports=[]` in spec file:
```python
hiddenimports=[
    ...,
    'missing.module.name',
]
```

### Issue: "Database is locked"

**Cause:** Multiple instances or orphaned process.

**Solution:**
- Single-instance mutex should prevent this
- Kill all instances: `taskkill /IM KeyloggerDetector.exe /F`

### Issue: Large EXE size (>100 MB)

**Solutions:**
1. Install UPX: Reduces size ~40%
2. Add exclusions to spec:
   ```python
   excludes=['matplotlib', 'scipy', 'pandas', 'IPython']
   ```
3. Consider `--onedir` mode

### Issue: Slow startup (>5 seconds)

**Causes:**
- UPX decompression
- Antivirus scanning `_MEI` folder

**Solutions:**
- Add `%TEMP%\_MEI*` to AV exclusions
- Use `--noupx` if speed is critical
- Consider `--onedir` mode

### Issue: Windows SmartScreen warning

**Solution:** Code-sign the executable with a trusted certificate.

---

## File Locations Reference

### Development

| File Type | Path |
|-----------|------|
| Source code | `<project_root>/src/` |
| Models | `<project_root>/models/` |
| Database | `<project_root>/logs/keylogger_events.db` |
| Logs | `<project_root>/logs/detector.log` |
| Whitelist | `<project_root>/data/whitelist.json` |

### Production (Frozen)

| File Type | Path |
|-----------|------|
| Executable | User chooses (portable) |
| Runtime temp | `%TEMP%\_MEI<random>\` (auto-deleted) |
| Models | `%LOCALAPPDATA%\KeyloggerDetector\models\` |
| Database | `%LOCALAPPDATA%\KeyloggerDetector\logs\keylogger_events.db` |
| Logs | `%LOCALAPPDATA%\KeyloggerDetector\logs\detector.log` |
| Whitelist | `%LOCALAPPDATA%\KeyloggerDetector\data\whitelist.json` |
| Quarantine | `%LOCALAPPDATA%\KeyloggerDetector\quarantine\` |

---

## Maintenance Notes

### Updating the Model

Users can update the ML model:
1. Train a new model: **Dashboard → Train Model tab**
2. Model is saved to: `%LOCALAPPDATA%\KeyloggerDetector\models\keylogger_detector_personalized.joblib`
3. Detector auto-reloads every 60 seconds

### Database Schema Changes

If you add new tables/columns:
1. Update `src/db_logger.py` schema SQL
2. Add migration logic or document manual steps
3. Test with fresh `keylogger_events.db` file

### Adding New Dependencies

When adding a new Python package:
1. Add to `requirements.txt`
2. Add to `hiddenimports=[]` in spec file (if needed)
3. Test frozen build

---

## Build Artifacts

After `.\build.ps1`:

```
dist/
  ├── KeyloggerDetector.exe           (45-90 MB depending on UPX)
  ├── README.txt                      (First-run instructions)
  └── models_optional/
      └── keylogger_detector.joblib   (If exists in source)

build/                                 (Intermediate files, can delete)
*.spec.bak                             (Backup from debug builds)
```

---

## Distribution Checklist

Before releasing:

- [ ] Build completes successfully
- [ ] Tested on clean Windows 10/11 machine
- [ ] All dashboard tabs function correctly
- [ ] Process detection and classification work
- [ ] Alert system fires correctly
- [ ] Actions (terminate, quarantine, whitelist) work
- [ ] Database persists across runs
- [ ] Single-instance enforcement works
- [ ] Logs are readable and helpful
- [ ] No hard-coded paths to developer's machine
- [ ] (Optional) Code-signed for SmartScreen
- [ ] README.txt included for end users

---

**Quick Build Commands:**

```powershell
# Development test
python main.py

# Clean build
.\build.ps1

# Debug build (console visible)
.\build.ps1 -Debug

# Test frozen executable
.\dist\KeyloggerDetector.exe

# Check logs
notepad $env:LOCALAPPDATA\KeyloggerDetector\logs\detector.log
```

---

**Version:** 1.0  
**Last Updated:** 2026-09-27  
**Maintainer:** Development Team
