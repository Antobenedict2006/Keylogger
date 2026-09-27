"""
feature_extractor.py
====================
Stage 2 of the pipeline: Feature Extraction Engine.

Responsibilities:
  - Maintain a rolling window of ProcessSnapshot objects per PID.
  - Compute per-process behavioural feature vectors from the rolling window.
  - Produce a FeatureVector dataclass (and a flat numpy array) ready for the
    ML classifier.
  - Track temporal signals: hook frequency over time, I/O burst patterns,
    etc.

Feature groups
--------------
  Group A – Hook & API signals
      hook_api_present         : 1 if user32.dll loaded, else 0
      has_ll_keyboard_hook     : 1 if WH_KEYBOARD_LL detected
      hook_related_dll_count   : # of hook-related DLLs loaded

  Group B – Visibility / UI
      has_visible_window       : 1 if process has visible window
      window_count             : number of visible windows owned

  Group C – Resource behaviour (rolling-window stats)
      cpu_mean                 : mean CPU% over window
      cpu_max                  : max CPU% over window
      mem_rss_mb_mean          : mean resident memory MB
      file_write_bytes_sum     : total file writes in window
      file_write_rate          : writes per second (window total / window span)
      open_file_count_mean     : mean open file handles
      net_connections_mean     : mean network connections
      net_bytes_sent_sum       : total bytes sent in window

  Group D – Binary / trust
      is_signed                : 1 if binary is signed (Authenticode)
      is_system_process        : 1 if classified as a Windows system process

  Group E – Persistence
      has_startup_entry        : 1 if found in Run registry keys

  Group F – Process metadata heuristics
      no_exe_path              : 1 if exe path is missing/empty
      cmdline_empty            : 1 if command line is empty
      name_length              : character length of process name
      running_from_temp        : 1 if exe lives under %TEMP% / AppData\\Local\\Temp
      running_from_appdata     : 1 if exe lives under AppData (non-Temp)
      age_seconds              : seconds since process was created

Total: 26 features (FEATURE_NAMES below matches this order exactly).

  Group H – Extended detection signals (NEW)
      has_kernel_hooks         : 1 if suspicious kernel drivers detected
      uses_raw_input_api       : 1 if raw keyboard input registered (hidden window)
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .monitor import ProcessSnapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature metadata
# ---------------------------------------------------------------------------

FEATURE_NAMES: List[str] = [
    # Group A
    "hook_api_present",
    "has_ll_keyboard_hook",
    "hook_related_dll_count",
    # Group B
    "has_visible_window",
    "window_count",
    # Group C
    "cpu_mean",
    "cpu_max",
    "mem_rss_mb_mean",
    "file_write_bytes_sum",
    "file_write_rate",
    "open_file_count_mean",
    "net_connections_mean",
    "net_bytes_sent_sum",
    # Group D
    "is_signed",
    "is_system_process",
    # Group E
    "has_startup_entry",
    # Group F
    "no_exe_path",
    "cmdline_empty",
    "name_length",
    "running_from_temp",
    "running_from_appdata",
    "age_seconds",
    # Group G (derived / composite)
    "hook_no_window",           # hook_api_present AND NOT has_visible_window
    "hook_with_network",        # hook_api_present AND net_connections_mean > 0
    # Group H – Extended detection signals (kernel + raw input)
    "has_kernel_hooks",         # suspicious kernel-mode driver detected
    "uses_raw_input_api",       # RegisterRawInputDevices keyboard + hidden window
]

NUM_FEATURES = len(FEATURE_NAMES)

# Rolling window size (number of snapshots retained per process)
WINDOW_SIZE = 10

# DLL names that are strongly associated with keyboard hooking
HOOK_RELATED_DLLS = {
    "user32.dll",
    "win32u.dll",
    "rawinput.dll",
    "dinput.dll",
    "dinput8.dll",
    "hid.dll",
    "hidparse.sys",
}

# ---------------------------------------------------------------------------
# Feature vector dataclass
# ---------------------------------------------------------------------------

@dataclass
class FeatureVector:
    """
    A fully extracted feature vector for one process, ready for classification.
    """
    pid: int
    name: str
    exe: Optional[str]
    snapshot_time: float

    features: np.ndarray = field(repr=False)   # shape (NUM_FEATURES,), dtype float32

    # Human-readable breakdown for alert explanations
    active_indicators: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {name: float(self.features[i]) for i, name in enumerate(FEATURE_NAMES)}

    def __repr__(self) -> str:
        indicators = ", ".join(self.active_indicators) or "none"
        return (
            f"FeatureVector(pid={self.pid}, name={self.name!r}, "
            f"indicators=[{indicators}])"
        )


# ---------------------------------------------------------------------------
# Per-process rolling history
# ---------------------------------------------------------------------------

class _ProcessHistory:
    """Maintains a fixed-size deque of ProcessSnapshot objects for one PID."""

    def __init__(self, window_size: int = WINDOW_SIZE) -> None:
        self._window: deque[ProcessSnapshot] = deque(maxlen=window_size)

    def add(self, snapshot: ProcessSnapshot) -> None:
        self._window.append(snapshot)

    @property
    def snapshots(self) -> List[ProcessSnapshot]:
        return list(self._window)

    @property
    def count(self) -> int:
        return len(self._window)

    def time_span(self) -> float:
        """Seconds between oldest and newest snapshot in the window."""
        snaps = self.snapshots
        if len(snaps) < 2:
            return WINDOW_SIZE * 5.0   # assume default interval
        return max(1.0, snaps[-1].snapshot_time - snaps[0].snapshot_time)


# ---------------------------------------------------------------------------
# Feature Extractor
# ---------------------------------------------------------------------------

class FeatureExtractor:
    """
    Maintains per-process rolling history and converts incoming
    ProcessSnapshot batches into FeatureVector objects.

    Usage::

        extractor = FeatureExtractor()
        vectors = extractor.update(snapshots)   # list[FeatureVector]
    """

    def __init__(self, window_size: int = WINDOW_SIZE) -> None:
        self._window_size = window_size
        self._histories: Dict[int, _ProcessHistory] = {}
        self._temp_dirs = self._resolve_temp_dirs()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, snapshots: List[ProcessSnapshot]) -> List[FeatureVector]:
        """
        Ingest a new batch of process snapshots.
        Returns one FeatureVector per process that has enough history.
        """
        # Update rolling histories
        active_pids = set()
        for snap in snapshots:
            active_pids.add(snap.pid)
            if snap.pid not in self._histories:
                self._histories[snap.pid] = _ProcessHistory(self._window_size)
            self._histories[snap.pid].add(snap)

        # Evict stale processes
        stale = [p for p in self._histories if p not in active_pids]
        for pid in stale:
            del self._histories[pid]

        # Extract a feature vector for every process that has ≥1 snapshot
        vectors: List[FeatureVector] = []
        for pid, history in self._histories.items():
            if history.count == 0:
                continue
            try:
                fv = self._extract(history)
                vectors.append(fv)
            except Exception as exc:
                logger.debug("Feature extraction failed for pid=%d: %s", pid, exc)

        return vectors

    def extract_single(self, snapshot: ProcessSnapshot) -> FeatureVector:
        """
        Convenience: ingest a single snapshot and return its feature vector
        immediately (useful for testing).
        """
        if snapshot.pid not in self._histories:
            self._histories[snapshot.pid] = _ProcessHistory(self._window_size)
        self._histories[snapshot.pid].add(snapshot)
        return self._extract(self._histories[snapshot.pid])

    # ------------------------------------------------------------------
    # Internal extraction logic
    # ------------------------------------------------------------------

    def _extract(self, history: _ProcessHistory) -> FeatureVector:
        snaps = history.snapshots
        latest = snaps[-1]
        span = history.time_span()

        # ---- Group A: Hook & API signals --------------------------------
        hook_api_present = int(
            "user32.dll" in latest.loaded_modules or latest.has_ll_keyboard_hook
        )
        has_ll_keyboard_hook = int(latest.has_ll_keyboard_hook)
        hook_related_dll_count = sum(
            1 for m in latest.loaded_modules if m in HOOK_RELATED_DLLS
        )

        # ---- Group B: Visibility / UI -----------------------------------
        has_visible_window = int(latest.has_visible_window)
        window_count = float(latest.window_count)

        # ---- Group C: Resource behaviour (rolling window) ---------------
        cpu_vals    = [s.cpu_percent for s in snaps]
        mem_vals    = [s.mem_rss_mb for s in snaps]
        file_writes = [s.file_write_bytes for s in snaps]
        open_files  = [s.open_file_count for s in snaps]
        net_conns   = [s.net_connections for s in snaps]
        net_sents   = [s.net_bytes_sent for s in snaps]

        cpu_mean           = float(np.mean(cpu_vals))
        cpu_max            = float(np.max(cpu_vals))
        mem_rss_mb_mean    = float(np.mean(mem_vals))
        file_write_bytes_sum = float(sum(file_writes))
        file_write_rate    = file_write_bytes_sum / span
        open_file_count_mean = float(np.mean(open_files))
        net_connections_mean = float(np.mean(net_conns))
        net_bytes_sent_sum = float(sum(net_sents))

        # ---- Group D: Binary / trust ------------------------------------
        is_signed        = int(latest.is_signed)
        is_system_process = int(latest.is_system_process)

        # ---- Group E: Persistence ---------------------------------------
        has_startup_entry = int(latest.has_startup_entry)

        # ---- Group F: Process metadata heuristics -----------------------
        no_exe_path  = int(not latest.exe)
        cmdline_empty = int(len(latest.cmdline) == 0)
        name_length  = float(len(latest.name))

        exe_lower = (latest.exe or "").lower()
        running_from_temp    = int(any(t in exe_lower for t in self._temp_dirs))
        running_from_appdata = int(
            "appdata" in exe_lower and not running_from_temp
        )

        age_seconds = float(
            time.time() - latest.create_time if latest.create_time else 0.0
        )

        # ---- Group G: Composite / derived -------------------------------
        hook_no_window   = int(hook_api_present and not has_visible_window)
        hook_with_network = int(
            hook_api_present and net_connections_mean > 0
        )

        # ---- Group H: Extended detection signals (kernel + raw input) ---
        # has_kernel_hooks – suspicious kernel-mode driver enumerated via
        # NtQuerySystemInformation (cached globally; O(1) per process).
        has_kernel_hooks = int(latest.has_kernel_hooks)

        # uses_raw_input_api – process has a hidden window AND registered
        # a raw keyboard input device via RegisterRawInputDevices.
        uses_raw_input_api = int(latest.uses_raw_input)

        # ---- Assemble array (order must match FEATURE_NAMES) ------------
        raw = [
            hook_api_present,
            has_ll_keyboard_hook,
            hook_related_dll_count,
            has_visible_window,
            window_count,
            cpu_mean,
            cpu_max,
            mem_rss_mb_mean,
            file_write_bytes_sum,
            file_write_rate,
            open_file_count_mean,
            net_connections_mean,
            net_bytes_sent_sum,
            is_signed,
            is_system_process,
            has_startup_entry,
            no_exe_path,
            cmdline_empty,
            name_length,
            running_from_temp,
            running_from_appdata,
            age_seconds,
            hook_no_window,
            hook_with_network,
            has_kernel_hooks,
            uses_raw_input_api,
        ]

        assert len(raw) == NUM_FEATURES, (
            f"Feature count mismatch: got {len(raw)}, expected {NUM_FEATURES}"
        )

        features = np.array(raw, dtype=np.float32)

        # ---- Build human-readable indicators for alert display ----------
        indicators = self._build_indicators(
            hook_api_present=hook_api_present,
            has_ll_keyboard_hook=has_ll_keyboard_hook,
            hook_no_window=hook_no_window,
            hook_with_network=hook_with_network,
            has_startup_entry=has_startup_entry,
            running_from_temp=running_from_temp,
            net_bytes_sent_sum=net_bytes_sent_sum,
            file_write_rate=file_write_rate,
            no_exe_path=no_exe_path,
            hook_related_dll_count=hook_related_dll_count,
            has_kernel_hooks=has_kernel_hooks,
            uses_raw_input_api=uses_raw_input_api,
        )

        return FeatureVector(
            pid=latest.pid,
            name=latest.name,
            exe=latest.exe,
            snapshot_time=latest.snapshot_time,
            features=features,
            active_indicators=indicators,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_temp_dirs() -> List[str]:
        """Return lowercased substrings that identify temp/staging paths."""
        dirs = [r"\temp\\", r"\tmp\\", r"\appdata\local\temp\\"]
        env_temp = os.environ.get("TEMP", "")
        if env_temp:
            dirs.append(env_temp.lower())
        return dirs

    @staticmethod
    def _build_indicators(
        hook_api_present: int,
        has_ll_keyboard_hook: int,
        hook_no_window: int,
        hook_with_network: int,
        has_startup_entry: int,
        running_from_temp: int,
        net_bytes_sent_sum: float,
        file_write_rate: float,
        no_exe_path: int,
        hook_related_dll_count: int,
        has_kernel_hooks: int = 0,
        uses_raw_input_api: int = 0,
    ) -> List[str]:
        """Return plain-English reasons this process was flagged."""
        reasons: List[str] = []

        if has_ll_keyboard_hook:
            reasons.append("Low-level keyboard hook (WH_KEYBOARD_LL) detected")
        elif hook_api_present:
            reasons.append("Keyboard hook APIs loaded (user32.dll)")

        if hook_no_window:
            reasons.append("Hooks keyboard input with no visible window")

        if hook_with_network:
            reasons.append("Keyboard hook combined with active network connections")

        if net_bytes_sent_sum > 1_000_000:
            reasons.append(
                f"High outbound network traffic "
                f"({net_bytes_sent_sum / 1024:.1f} KB sent in scan window)"
            )

        if file_write_rate > 50_000:
            reasons.append(
                f"High file-write rate ({file_write_rate / 1024:.1f} KB/s)"
            )

        if has_startup_entry:
            reasons.append("Registered in Windows startup (Run key)")

        if running_from_temp:
            reasons.append("Executable running from a temporary directory")

        if no_exe_path:
            reasons.append("No executable path — possibly injected / fileless")

        if hook_related_dll_count >= 3:
            reasons.append(
                f"{hook_related_dll_count} hook-related DLLs loaded simultaneously"
            )

        # Group H – extended signals
        if has_kernel_hooks:
            reasons.append(
                "Suspicious kernel-mode driver detected (possible rootkit/keylogger)"
            )

        if uses_raw_input_api:
            reasons.append(
                "Raw keyboard input registered on hidden window (raw input keylogger pattern)"
            )

        return reasons
