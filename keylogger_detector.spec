# -*- mode: python ; coding: utf-8 -*-
"""
keylogger_detector.spec
=======================
PyInstaller build specification for the AI-Based Keylogger Detection System.

Usage
-----
  pyinstaller keylogger_detector.spec

Output
------
  dist/KeyloggerDetector.exe   — standalone Windows executable

Build modes
-----------
  This spec produces a WINDOWED application (no console) with a system tray icon.
  Users can still see logs via the dashboard or the log file.

  To debug startup issues, temporarily change console=False to console=True
  in the EXE() call below.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import sys
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------------
# Source analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Note: These files are optional. If they don't exist, they'll be created
        # at runtime in %LOCALAPPDATA%\KeyloggerDetector\
        # Only include them if they exist during build:
        # ('models/*.joblib', 'models'),
        # ('models/*.json', 'models'),
        # ('data/typing_baseline.json', 'data'),
        # ('data/mouse_baseline.json', 'data'),
        # ('data/whitelist.json', 'data'),
    ],
    hiddenimports=[
        # Core ML dependencies
        'sklearn.ensemble',
        'sklearn.tree',
        'sklearn.preprocessing',
        'sklearn.pipeline',
        'joblib',
        'numpy',
        
        # Process monitoring
        'psutil',
        
        # UI dependencies
        'tkinter',
        'tkinter.ttk',
        'tkinter.font',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'pystray',
        
        # Notifications
        'plyer',
        'plyer.platforms.win.notification',
        
        # Behavioral analysis (optional)
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
        
        # Database
        'sqlite3',
        
        # Multiprocessing
        'multiprocessing',
        'multiprocessing.spawn',
        
        # Project modules
        'src.monitor',
        'src.feature_extractor',
        'src.classifier',
        'src.alert_manager',
        'src.db_logger',
        'src.behavioral_analyzer',
        'src.paths',
        'src.ui.dashboard',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused packages to reduce .exe size and build time
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        # Web frameworks (removed)
        'flask',
        'flask_cors',
        'jinja2',
        'werkzeug',
        # Don't exclude setuptools/distutils - causes issues
        # Exclude deep learning frameworks (not used)
        'torch',
        'torchvision',
        'tensorflow',
        'keras',
        # Exclude symbolic math (not used)
        'sympy',
        'mpmath',
        # Exclude testing frameworks
        'unittest',
        'nose',
        'py',
        'pygments',
        # Exclude documentation tools
        'sphinx',
        'docutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ---------------------------------------------------------------------------
# PYZ (compressed archive of pure Python modules)
# ---------------------------------------------------------------------------

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# ---------------------------------------------------------------------------
# EXE (the final executable)
# ---------------------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='KeyloggerDetector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # Compress with UPX if available (reduces size ~40%)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,               # WINDOWED mode — no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',             # Application icon (create this if it doesn't exist)
    version_file=None,           # Optional: create a version_info.txt for metadata
)

# ---------------------------------------------------------------------------
# Optional: COLLECT (for --onedir mode, disabled here)
# ---------------------------------------------------------------------------
# We're using --onefile mode (everything in a single .exe) so no COLLECT step.
# If you want --onedir (exe + _internal folder), uncomment below:
#
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='KeyloggerDetector',
# )
