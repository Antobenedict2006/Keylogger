# AI-Based Keylogger Detection System

> **Modern, ML-powered threat detection for Windows with a clean, professional UI**

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

---

## 🚀 What's New in v1.0

### ✨ Modernized UI
- **Clean, light theme** - Professional appearance with better readability
- **Interactive statistics cards** - Click cards to filter detections instantly
- **Modern design** - Segoe UI font, improved spacing, hover effects
- **Better UX** - Intuitive navigation and visual feedback

### 📦 Standalone Executable
- **Single .exe file** - No Python installation required
- **50-70 MB** - Optimized with UPX compression
- **Professional icon** - Custom shield design
- **Automated build** - PowerShell script for easy compilation

---

## 📋 Table of Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Building Executable](#building-executable)
- [Architecture](#architecture)
- [Contributing](#contributing)
- [License](#license)

---

## ✨ Features

### 🔍 Detection Capabilities
- **Real-time monitoring** - Continuous process scanning every 5 seconds
- **ML-based detection** - Trained scikit-learn model for accurate threat identification
- **Heuristic fallback** - Works without trained model using pattern matching
- **Multi-factor analysis** - Keyboard hooks, window visibility, system processes, startup entries

### 🎯 User Interface
- **Live Alerts** - Real-time threat list with action buttons
- **Detection History** - Filterable database of all past detections
- **Statistics Dashboard** - Interactive cards showing threat summaries
- **System Tray Integration** - Minimize to tray, pause/resume monitoring

### ⚡ Actions & Responses
- **Terminate** - Kill suspicious processes immediately
- **Quarantine** - Move executable to secure location
- **Whitelist** - Mark trusted applications
- **Dismiss** - Remove from active alerts

### 📊 Logging & Persistence
- **SQLite database** - All detections and actions logged
- **Audit trail** - Complete history for forensics
- **Process snapshots** - Optional raw data logging for retraining

---

## 📸 Screenshots

### Statistics Dashboard (Interactive Cards)
```
┌─────────────────────────────────────────────────────────┐
│  Detection Statistics                                    │
│                                                          │
│  ╔══════╗  ╔══════╗  ╔══════╗  ╔══════╗               │
│  ║  543 ║  ║  47  ║  ║  496 ║  ║   0  ║               │
│  ║Total ║  ║Malic-║  ║Susp- ║  ║Acti- ║               │
│  ║Detec ║  ║ious  ║  ║icious║  ║oned  ║               │
│  ║Click ║  ║Click ║  ║Click ║  ║Click ║               │
│  ║filter║  ║filter║  ║filter║  ║filter║               │
│  ╚══════╝  ╚══════╝  ╚══════╝  ╚══════╝               │
│                                                          │
│  Actions Taken                                           │
│  ┌────────────────────────────────────────────┐        │
│  │  Terminate      2                          │        │
│  │  Whitelist      1                          │        │
│  └────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────┘
```

### Live Alerts Tab
- Real-time threat list with PID, process name, risk level, score
- Action buttons: Terminate, Quarantine, Whitelist, Dismiss
- Color-coded risk levels: Red (Malicious), Orange (Suspicious)

### History Tab
- Filterable by risk level and time range
- Double-click for detailed information
- Searchable detection database

---

## 🚀 Quick Start

### For Users (Standalone Executable)

1. **Download** `KeyloggerDetector.exe`
2. **Run** by double-clicking
3. **Allow** Windows SmartScreen if prompted
4. **Monitor** threats in real-time

### For Developers (From Source)

```powershell
# 1. Clone repository
git clone https://github.com/yourusername/keylogger-detector.git
cd keylogger-detector

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run application
python main.py

# 4. (Optional) Train ML model
python tools/train_model.py
```

See [QUICK_START.md](QUICK_START.md) for detailed instructions.

---

## 💻 Installation

### System Requirements
- **OS:** Windows 10/11 (64-bit)
- **Python:** 3.8 or higher (for source)
- **RAM:** 200-400 MB
- **Disk:** 100 MB + database growth

### Dependencies

```txt
psutil==5.9.8          # Process monitoring
pywin32==306           # Windows API access
scikit-learn==1.4.2    # Machine learning
pandas==2.2.2          # Data processing
numpy==1.26.4          # Numerical operations
joblib==1.4.2          # Model serialization
plyer==2.1.0           # Desktop notifications
pystray==0.19.5        # System tray icon
Pillow==10.3.0         # Image processing
pyinstaller==6.3.0     # Executable creation
```

Install with:
```powershell
pip install -r requirements.txt
```

---

## 🎮 Usage

### Command Line Options

```powershell
# Show help
python main.py --help

# Run without GUI (headless mode)
python main.py --no-gui

# Custom scan interval (seconds)
python main.py --scan-interval 10

# Custom database location
python main.py --db C:\Logs\detections.db

# Verbose logging
python main.py --log-level DEBUG

# Custom ML model
python main.py --model models\custom_model.joblib

# Alert threshold (suspicious or malicious)
python main.py --alert-threshold malicious

# Log all process snapshots (increases DB size)
python main.py --log-snapshots
```

### Using the Dashboard

#### 1. Live Alerts Tab
- View real-time threats as detected
- Select a threat and click action buttons
- **Terminate:** Kill the process
- **Quarantine:** Move to secure location
- **Whitelist:** Mark as trusted
- **Dismiss:** Remove from view

#### 2. History Tab
- View all past detections
- **Filter by risk:** All, Malicious, Suspicious
- **Time range:** Last X hours
- **Double-click** any row for details

#### 3. Statistics Tab
- **Click cards** to filter History:
  - Total → Show all
  - Malicious → Show only malicious
  - Suspicious → Show only suspicious
  - Actioned → Show handled threats
- View action breakdown
- Monitor detection engine status

#### System Tray
- **Left-click:** Open dashboard
- **Right-click:**
  - Open Dashboard
  - Pause/Resume Monitoring
  - Quit

---

## 🏗️ Building Executable

### Automated Build (Recommended)

```powershell
# Simple build
.\build.ps1

# Clean build (removes cache)
.\build.ps1 -Clean

# Verbose output
.\build.ps1 -Verbose
```

### Manual Build

```powershell
# 1. Create application icon
python create_icon.py

# 2. Build with PyInstaller
pyinstaller keylogger_detector.spec

# 3. Find output
# dist\KeyloggerDetector.exe (~50-70 MB)
```

### Build Output
- **Single file:** `dist/KeyloggerDetector.exe`
- **Size:** 50-70 MB (with UPX compression)
- **Includes:** Python + all dependencies + ML model
- **Runs on:** Any Windows 10/11 PC (no Python needed)

See [BUILD_INSTRUCTIONS.md](BUILD_INSTRUCTIONS.md) for detailed guide.

---

## 🏛️ Architecture

### Pipeline Flow

```
ProcessMonitor → FeatureExtractor → KeyloggerClassifier
                                   ↓
                              AlertManager → DBLogger
                                   ↓
                              Dashboard (UI)
```

### Components

#### 1. **ProcessMonitor** (`src/monitor.py`)
- Scans running processes every N seconds
- Extracts process metadata (PID, name, executable path)
- Detects keyboard hooks, windows, startup entries

#### 2. **FeatureExtractor** (`src/feature_extractor.py`)
- Converts process snapshots to feature vectors
- Calculates CPU%, memory, network connections
- Tracks process behavior over time

#### 3. **KeyloggerClassifier** (`src/classifier.py`)
- ML-based threat scoring (scikit-learn)
- Heuristic fallback when no model available
- Hot-reload support for model updates

#### 4. **AlertManager** (`src/alert_manager.py`)
- Manages active alerts
- Handles user actions (terminate, quarantine, etc.)
- Sends desktop notifications

#### 5. **DBLogger** (`src/db_logger.py`)
- SQLite persistence layer
- Logs all detections and actions
- Provides query interface for UI

#### 6. **Dashboard** (`src/ui/dashboard.py`)
- Tkinter-based GUI
- Three tabs: Live Alerts, History, Statistics
- System tray integration
- **NEW:** Modern design with interactive elements

### Database Schema

```sql
-- Detections table
CREATE TABLE detections (
    id INTEGER PRIMARY KEY,
    pid INTEGER,
    process_name TEXT,
    exe_path TEXT,
    risk_level TEXT,        -- malicious | suspicious | safe
    score REAL,
    confidence REAL,
    reasons TEXT,           -- JSON array
    model_version TEXT,
    detected_at REAL,
    actioned INTEGER
);

-- Actions table
CREATE TABLE actions (
    id INTEGER PRIMARY KEY,
    detection_id INTEGER,
    pid INTEGER,
    process_name TEXT,
    action TEXT,            -- terminate | quarantine | whitelist | dismiss
    success INTEGER,
    message TEXT,
    acted_at REAL
);

-- Process snapshots (optional, audit trail)
CREATE TABLE process_snapshots (
    id INTEGER PRIMARY KEY,
    pid INTEGER,
    process_name TEXT,
    exe_path TEXT,
    has_hook INTEGER,
    has_window INTEGER,
    cpu_percent REAL,
    mem_rss_mb REAL,
    net_connections INTEGER,
    has_startup INTEGER,
    is_system INTEGER,
    snapshot_time REAL
);
```

---

## 🔧 Configuration

### Model Training

```powershell
# Train with synthetic data
python tools/train_model.py

# Output: models/keylogger_detector.joblib

# Customize in tools/train_model.py:
# - Training data generation
# - Feature importance
# - Model hyperparameters
```

### Whitelist Management

Add trusted processes to avoid false positives:
1. Detect a process
2. Click "Whitelist" button
3. Process is added to `whitelist.txt`

### Logging Configuration

```powershell
# Enable debug logging
python main.py --log-level DEBUG --log-file logs/debug.log

# Log all process snapshots (for retraining)
python main.py --log-snapshots
```

---

## 🧪 Testing

### UI Test Mode

```powershell
# Test UI with mock data
python test_ui.py

# Verify:
# - Modern styling
# - Interactive cards
# - Tab navigation
# - Detail popups
```

### Manual Testing

1. **Detection test:** Run a legitimate app with keyboard hooks (IDE, AutoHotkey)
2. **Action test:** Try Terminate/Whitelist/Dismiss
3. **Filter test:** Click statistic cards, verify History tab filters
4. **Persistence test:** Close and reopen, verify detections remain

---

## 📚 Documentation

- **[QUICK_START.md](QUICK_START.md)** - Getting started guide
- **[BUILD_INSTRUCTIONS.md](BUILD_INSTRUCTIONS.md)** - Detailed build guide
- **[MODERNIZATION_SUMMARY.md](MODERNIZATION_SUMMARY.md)** - UI changes documentation
- **[Prism documents/](Prism%20documents/)** - Design documents (PRISM framework)

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```powershell
# Install dev dependencies
pip install -r requirements.txt

# Run tests
python test_ui.py

# Build and test
.\build.ps1
.\dist\KeyloggerDetector.exe
```

---

## 🐛 Known Issues

### False Positives
- **Issue:** Legitimate apps with keyboard hooks flagged
- **Workaround:** Use Whitelist button
- **Fix:** Train model with more diverse dataset

### Antivirus Warnings
- **Issue:** PyInstaller .exe flagged by some antivirus
- **Cause:** Signature-based false positive
- **Solutions:**
  - Add to antivirus exclusions
  - Code sign the executable (requires certificate)
  - Distribute source code for technical users

### Large Executable Size
- **Issue:** 50-70 MB file size
- **Cause:** Bundled Python + ML libraries
- **Optimization:** Use UPX compression (already enabled)

---

## 🛣️ Roadmap

### v1.1 (Planned)
- [ ] Export detections to CSV/PDF
- [ ] Chart visualizations for statistics
- [ ] Search functionality across tabs
- [ ] Bulk actions (select multiple, act on all)

### v2.0 (Future)
- [ ] Dark mode toggle
- [ ] Custom themes
- [ ] Email alerts
- [ ] Remote monitoring
- [ ] Multi-language support
- [ ] Auto-update mechanism

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **scikit-learn** - Machine learning framework
- **Tkinter** - GUI toolkit
- **PyInstaller** - Executable creation
- **pystray** - System tray integration
- **psutil** - Process monitoring

---

## 📧 Contact

- **Issues:** [GitHub Issues](https://github.com/yourusername/keylogger-detector/issues)
- **Discussions:** [GitHub Discussions](https://github.com/yourusername/keylogger-detector/discussions)

---

## 🎯 Project Status

**Current Version:** 1.0.0  
**Status:** Active Development  
**Last Updated:** September 17, 2026

---

**⚠️ Disclaimer:** This tool is for educational and security research purposes. Always comply with local laws and regulations when monitoring systems.