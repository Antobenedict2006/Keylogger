# Scripts Folder

This folder contains all build scripts, test scripts, and utility scripts for the AI-Based Keylogger Detection System.

---

## Build Scripts

### `build.ps1`
**Usage**: `.\scripts\build.ps1 -Clean`

Builds the standalone Windows executable using PyInstaller.

**Options**:
- `-Clean` - Removes previous build artifacts before building

**Output**: `dist\KeyloggerDetector.exe`

---

## Test Scripts (`tests/`)

Located in: `scripts\tests\`

- `test_ui.py` - Tests the Tkinter dashboard interface
- `test_phase2_behavioral.py` - Tests behavioral analysis engine
- `test_mouse_optimization.py` - Tests mouse tracking optimization
- `test_recording_debug.py` - Debugs the process recording feature

**Usage**:
```powershell
python scripts\tests\test_ui.py
```

---

## Utility Scripts (`utilities/`)

Located in: `scripts\utilities\`

### Data Verification
- `check_training_data.py` - Checks baseline training progress
- `check_recording_table.py` - Inspects process recording database
- `check_todays_recording.py` - Shows recordings from today

### Data Export
- `manual_export_csv.py` - Manually exports recording sessions to CSV

### Asset Generation
- `create_icon.py` - Generates the application icon

**Usage**:
```powershell
python scripts\utilities\check_training_data.py
python scripts\utilities\manual_export_csv.py
```

---

## Running from Different Locations

### From Project Root:
```powershell
.\scripts\build.ps1 -Clean
python scripts\utilities\check_training_data.py
```

### From Scripts Folder:
```powershell
cd scripts
.\build.ps1 -Clean
python utilities\check_training_data.py
```

---

## Notes

- All paths in scripts are relative to the project root
- Build script automatically finds `config\keylogger_detector.spec`
- Build script looks for icon at `assets\icon.ico`
- Test scripts should be run from project root for correct imports
