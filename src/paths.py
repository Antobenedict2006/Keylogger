r"""
paths.py
========
Centralized path resolution for all persistent files (models, databases, logs,
quarantine, whitelist).

PyInstaller behavior
--------------------
  When frozen (running as keylogger_detector.exe), __file__ points to:
      C:\Users\<user>\AppData\Local\Temp\_MEI<random>\src\paths.py

  sys._MEIPASS exists and points to the unpacked runtime root:
      C:\Users\<user>\AppData\Local\Temp\_MEI<random>

  User-writable data files MUST go into %LOCALAPPDATA%\KeyloggerDetector
  so they persist across runs and are not lost when the temp folder is wiped.

File categories
---------------
  READ-ONLY (bundled, in temp when frozen):
      None currently - the trained model is user-writable so it can be
      replaced or updated via the Train tab.

  USER-WRITABLE (persistent across runs):
      models/                 - trained .joblib files
      logs/                   - SQLite DB, detector.log
      data/                   - whitelist.json, behavioral profiles
      quarantine/             - quarantined executables

Resolution strategy
-------------------
  1. If frozen (hasattr sys, '_MEIPASS'), user data goes to:
         %LOCALAPPDATA%\KeyloggerDetector\<subpath>

  2. If not frozen (dev mode), resolve relative to project root (parent of src/).

Usage
-----
  from src.paths import get_data_path

  db_path        = get_data_path("logs", "keylogger_events.db")
  model_path     = get_data_path("models", "keylogger_detector.joblib")
  whitelist_path = get_data_path("data", "whitelist.json")
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Detection of frozen / packaged state
# ---------------------------------------------------------------------------

def is_frozen() -> bool:
    """Return True if running as a PyInstaller-frozen executable."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_meipass() -> Optional[Path]:
    """Return sys._MEIPASS as a Path if it exists, else None."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


# ---------------------------------------------------------------------------
# User data root directory
# ---------------------------------------------------------------------------

def get_user_data_root() -> Path:
    """
    Return the root directory for all user-writable persistent data.

    - When frozen:  %LOCALAPPDATA%\\KeyloggerDetector
    - When dev:     <project_root>  (parent of src/)

    Creates the directory if it does not exist.
    """
    if is_frozen():
        # Windows %LOCALAPPDATA% = C:\Users\<username>\AppData\Local
        local_appdata = Path.home() / "AppData" / "Local"
        root = local_appdata / "KeyloggerDetector"
    else:
        # Dev mode: resolve from this file's parent (src/) → project root
        root = Path(__file__).parent.parent.resolve()

    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------

def get_data_path(*subpath_parts: str) -> Path:
    """
    Build an absolute path under the user data root.

    Example::

        get_data_path("logs", "keylogger_events.db")
        → dev:    <project_root>/logs/keylogger_events.db
        → frozen: %LOCALAPPDATA%/KeyloggerDetector/logs/keylogger_events.db

    Creates parent directories if necessary.
    """
    root = get_user_data_root()
    full_path = root.joinpath(*subpath_parts)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    return full_path


def get_bundled_resource_path(*subpath_parts: str) -> Path:
    """
    Build an absolute path for a bundled read-only resource.

    Currently unused — all files are user-writable.  Reserved for assets
    (icons, config templates) that are packed with the .exe via PyInstaller
    --add-data and live in sys._MEIPASS when frozen.

    Example::

        icon_path = get_bundled_resource_path("assets", "icon.ico")
        → frozen: C:\\Users\\...\\Temp\\_MEI<random>\\assets\\icon.ico
        → dev:    <project_root>/assets/icon.ico
    """
    if is_frozen():
        meipass = get_meipass()
        return meipass.joinpath(*subpath_parts) if meipass else Path(*subpath_parts)
    root = Path(__file__).parent.parent.resolve()
    return root.joinpath(*subpath_parts)


# ---------------------------------------------------------------------------
# Common paths (convenience accessors)
# ---------------------------------------------------------------------------

def get_models_dir() -> Path:
    return get_data_path("models")


def get_logs_dir() -> Path:
    return get_data_path("logs")


def get_data_dir() -> Path:
    return get_data_path("data")


def get_quarantine_dir() -> Path:
    return get_data_path("quarantine")


# ---------------------------------------------------------------------------
# Defaults used by the pipeline
# ---------------------------------------------------------------------------

DEFAULT_MODEL_PATH               = get_data_path("models", "keylogger_detector.joblib")
DEFAULT_MODEL_PATH_PERSONALIZED  = get_data_path("models", "keylogger_detector_personalized.joblib")

DEFAULT_DB_PATH                  = get_data_path("logs", "keylogger_events.db")
DEFAULT_LOG_FILE                 = get_data_path("logs", "detector.log")

DEFAULT_WHITELIST_PATH           = get_data_path("data", "whitelist.json")
DEFAULT_TYPING_BASELINE_PATH     = get_data_path("data", "typing_baseline.json")
DEFAULT_MOUSE_BASELINE_PATH      = get_data_path("data", "mouse_baseline.json")

DEFAULT_QUARANTINE_DIR           = get_quarantine_dir()
