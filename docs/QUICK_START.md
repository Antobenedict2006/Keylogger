# Quick Start Guide

## For End Users (Running the .exe)

### Download and Run
1. Download `KeyloggerDetector.exe`
2. Double-click to run
3. If Windows SmartScreen appears, click "More info" → "Run anyway"
4. The system tray icon will appear (blue shield)
5. Dashboard opens automatically

### Using the Application

#### Live Alerts Tab
- Shows real-time threats as they're detected
- Select a row, then click action buttons:
  - **🗙 Terminate** - Kill the process
  - **🔒 Quarantine** - Move to secure location
  - **✓ Whitelist** - Mark as safe (won't alert again)
  - **✕ Dismiss** - Remove from live view
- Double-click a row for detailed information

#### History Tab
- View all past detections
- **Filter by Risk:** Choose All/Malicious/Suspicious
- **Time Range:** Adjust hours to look back
- Click **🔄 Refresh** to update
- Double-click for details

#### Statistics Tab
- **Click any card** to filter the History tab:
  - **Total** → Show all detections
  - **Malicious** → Show only malicious threats
  - **Suspicious** → Show only suspicious processes
  - **Actioned** → Show all handled threats
- Hover over cards to see them highlight
- View action breakdown and engine status

#### System Tray
- **Left-click:** Open dashboard
- **Right-click menu:**
  - Open Dashboard
  - Pause/Resume Monitoring
  - Quit

### Command Line Options
```powershell
# Show help
KeyloggerDetector.exe --help

# Run without GUI (service mode)
KeyloggerDetector.exe --no-gui

# Custom scan interval (seconds)
KeyloggerDetector.exe --scan-interval 10

# Custom database location
KeyloggerDetector.exe --db C:\Logs\detections.db

# Verbose logging
KeyloggerDetector.exe --log-level DEBUG
```

---

## For Developers (Building from Source)

### Prerequisites
```powershell
# Install Python 3.8 or higher
# Download from: https://www.python.org/downloads/

# Install dependencies
pip install -r requirements.txt
```

### Running from Source
```powershell
# Standard GUI mode
python main.py

# Headless mode
python main.py --no-gui

# With custom options
python main.py --scan-interval 5 --log-level DEBUG
```

### Building the Executable

#### Method 1: Automated Script (Recommended)
```powershell
# Simple build
.\build.ps1

# Clean build (removes cache)
.\build.ps1 -Clean

# Verbose output (for debugging)
.\build.ps1 -Verbose
```

#### Method 2: Manual Build
```powershell
# 1. Create icon
python create_icon.py

# 2. Build with PyInstaller
pyinstaller keylogger_detector.spec

# 3. Find output
# dist\KeyloggerDetector.exe
```

### Project Structure
```
Keylogger/
├── main.py                    # Entry point
├── src/
│   ├── monitor.py             # Process monitoring
│   ├── feature_extractor.py   # Feature engineering
│   ├── classifier.py          # ML threat detection
│   ├── alert_manager.py       # Alert handling
│   ├── db_logger.py           # Database logging
│   └── ui/
│       └── dashboard.py       # Tkinter UI (MODERNIZED)
├── tools/
│   └── train_model.py         # Model training
├── models/
│   └── *.joblib               # Trained models
├── logs/
│   └── *.db                   # SQLite database
├── requirements.txt           # Python dependencies
├── keylogger_detector.spec    # PyInstaller config
├── build.ps1                  # Build automation
├── create_icon.py             # Icon generator
└── BUILD_INSTRUCTIONS.md      # Detailed build guide
```

### Training the ML Model
```powershell
# Generate synthetic training data
python tools\train_model.py

# Output: models/keylogger_detector.joblib
```

### Development Workflow
```powershell
# 1. Make changes to code

# 2. Test locally
python main.py

# 3. Build executable
.\build.ps1

# 4. Test on clean machine
# Copy dist\KeyloggerDetector.exe to a PC without Python
```

---

## Common Issues

### Issue: "Python not found"
**Solution:** Install Python 3.8+ from https://www.python.org/downloads/
- ✅ Check "Add Python to PATH" during installation

### Issue: "Module not found" errors
**Solution:** Install dependencies
```powershell
pip install -r requirements.txt
```

### Issue: Build fails with sklearn errors
**Solution:** Ensure sklearn is installed correctly
```powershell
pip uninstall scikit-learn
pip install scikit-learn==1.4.2
```

### Issue: Executable is too large (>100 MB)
**Solution:** Install UPX compressor
1. Download from: https://github.com/upx/upx/releases
2. Extract to `C:\Tools\upx`
3. Add to PATH
4. Rebuild: `.\build.ps1 -Clean`

### Issue: Antivirus blocks the .exe
**Solution:** Add exception or use code signing
```powershell
# Windows Defender exclusion
Add-MpPreference -ExclusionPath "C:\path\to\KeyloggerDetector.exe"
```

### Issue: "Icon not found" during build
**Solution:** Generate icon
```powershell
python create_icon.py
```

### Issue: ML model not loading
**Solution:** Train the model first
```powershell
python tools\train_model.py
```

---

## Feature Highlights

### ✨ What's New (v1.0)

#### Modern UI
- ✅ Clean, light theme (no more dark clutter)
- ✅ Professional Segoe UI font
- ✅ Better spacing and readability
- ✅ Hover effects on all buttons

#### Interactive Statistics
- ✅ **Click cards to filter** - Click "Malicious" card → History tab shows only malicious
- ✅ Visual hover feedback
- ✅ Smooth tab switching
- ✅ Auto-filtering

#### Standalone Executable
- ✅ Single .exe file (~80 MB)
- ✅ No Python required
- ✅ Includes ML model
- ✅ Professional icon
- ✅ System tray integration

---

## Performance Expectations

### System Requirements
- **OS:** Windows 10/11 (64-bit)
- **RAM:** 200-400 MB
- **Disk:** 100 MB (exe) + 50 MB (database growth)
- **CPU:** Minimal (<5% average)

### Detection Speed
- **Scan interval:** 5 seconds (configurable)
- **Processes per scan:** 50-200 typical
- **Detection time:** <100ms per process
- **Database writes:** <50ms

### Resource Usage
- **Idle:** 50-100 MB RAM, <1% CPU
- **Active scan:** 150-250 MB RAM, 3-8% CPU
- **Peak (alert):** 200-400 MB RAM, 5-12% CPU

---

## Keyboard Shortcuts

While not officially supported, these Windows shortcuts work:

- **Alt + F4** - Close window (minimizes to tray)
- **Ctrl + Tab** - Next tab
- **Ctrl + Shift + Tab** - Previous tab
- **F5** - Refresh (in History tab, after clicking Refresh button)

---

## Configuration Files

### Database Location
Default: `logs/keylogger_events.db`

Change with:
```powershell
KeyloggerDetector.exe --db C:\Custom\Path\db.db
```

### Log Files
Default: `logs/detector.log`

Change with:
```powershell
KeyloggerDetector.exe --log-file C:\Custom\Path\app.log
```

### Model File
Default: `models/keylogger_detector.joblib`

Change with:
```powershell
KeyloggerDetector.exe --model C:\Custom\Path\model.joblib
```

---

## Update Process

### For Users
1. Download new `KeyloggerDetector.exe`
2. Close the old application (right-click tray icon → Quit)
3. Replace the old .exe
4. Run the new version
5. Your database and settings are preserved

### For Developers
```powershell
# 1. Pull latest code
git pull origin main

# 2. Update dependencies
pip install -r requirements.txt --upgrade

# 3. Rebuild
.\build.ps1 -Clean

# 4. Test
.\dist\KeyloggerDetector.exe
```

---

## Support & Documentation

- **Full Build Guide:** `BUILD_INSTRUCTIONS.md`
- **Detailed Summary:** `MODERNIZATION_SUMMARY.md`
- **Project README:** `README.md`
- **Training Guide:** `tools/train_model.py` (see comments)

---

## License & Security

### Running as Administrator
The application **does not require** administrator privileges for basic monitoring. However, some actions do:

- **Terminate process:** May require admin for system processes
- **Quarantine:** Requires write access to quarantine folder

To run as admin:
- Right-click `KeyloggerDetector.exe` → "Run as administrator"

### Security Considerations
- ✅ All detections are logged locally (no cloud uploads)
- ✅ No network communication (except optional updates)
- ✅ Database is SQLite (readable with any SQLite browser)
- ✅ Open source (audit the code yourself)

### Privacy
- ✅ No telemetry or tracking
- ✅ No user data collection
- ✅ All data stays on your machine
- ✅ You control the database

---

## Credits

**Original Application:** AI-Based Keylogger Detection System
**UI Modernization:** 2026-09-17
**Framework:** Python + Tkinter
**ML Library:** scikit-learn
**Packaging:** PyInstaller

---

**Last Updated:** September 17, 2026
**Version:** 1.0.0
