# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for AI Keylogger Detection System
========================================================

This spec file creates a single-file Windows executable with all dependencies.

To build:
    pyinstaller keylogger_detector.spec

Output:
    dist/KeyloggerDetector.exe (single file, ~50-80 MB)
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Application metadata
APP_NAME = 'KeyloggerDetector'
APP_VERSION = '1.0.0'
APP_AUTHOR = 'Your Name'

# Collect all sklearn submodules (required for ML model)
sklearn_modules = collect_submodules('sklearn')

# Additional hidden imports
hidden_imports = [
    'sklearn.ensemble',
    'sklearn.tree',
    'sklearn.neighbors',
    'sklearn.neural_network',
    'sklearn.utils._typedefs',
    'sklearn.utils._heap',
    'sklearn.utils._sorting',
    'sklearn.utils._vector_sentinel',
    'tkinter',
    'tkinter.ttk',
    'tkinter.messagebox',
    'psutil',
    'sqlite3',
    'queue',
    'threading',
    'json',
    'pathlib',
    'logging',
    'time',
    'pystray',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageTk',
    'joblib',
    'numpy',
    'pandas',
] + sklearn_modules

# Data files to include (ML model, database, etc.)
datas = [
    ('models/keylogger_detector.joblib', 'models'),  # ML model
    # Add any other data files here
]

# Binary exclusions (reduce file size)
excluded_binaries = []

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',  # Not used
        'scipy',       # Not used
        'IPython',     # Not used
        'jupyter',     # Not used
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress with UPX (reduces size by ~30%)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window (GUI mode)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',  # Application icon
    version_file=None,
)
