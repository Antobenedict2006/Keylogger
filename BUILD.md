# Quick Build Guide

## Building the Executable

From the project root directory:

```powershell
.\scripts\build.ps1 -Clean
```

This will:
1. Clean previous builds (if `-Clean` flag used)
2. Verify Python and PyInstaller are installed
3. Check that the icon file exists at `assets\icon.ico`
4. Run PyInstaller with the spec file from `config\keylogger_detector.spec`
5. Create `dist\KeyloggerDetector.exe`

## Testing

```powershell
.\dist\KeyloggerDetector.exe
```

## Project Structure

```
Keylogger/
├── main.py                    # Entry point
├── README.md                  # Main documentation
├── BUILD.md                   # This file
│
├── assets/                    # Icons and resources
│   ├── icon.ico
│   ├── icon.png
│   └── loading_screen_design/
│
├── config/                    # Configuration files
│   ├── keylogger_detector.spec  # PyInstaller spec
│   └── requirements.txt         # Python dependencies
│
├── scripts/                   # Build and utility scripts
│   ├── build.ps1             # Main build script
│   ├── tests/                # Test scripts
│   └── utilities/            # Helper scripts
│
├── src/                       # Source code
│   ├── monitor.py
│   ├── classifier.py
│   ├── behavioral_analyzer.py
│   └── ui/
│
├── data/                      # Runtime data
├── models/                    # ML models
├── logs/                      # Log files
├── docs/                      # Documentation
├── tools/                     # Training tools
├── dist/                      # Built executable
└── build/                     # Build artifacts
```

## For More Information

See `docs/BUILD_INSTRUCTIONS.md` for detailed build instructions.
