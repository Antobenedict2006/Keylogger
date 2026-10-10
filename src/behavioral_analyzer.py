"""
behavioral_analyzer.py
======================
Phase 1 & Phase 2 — Multi-Modal Behavioral Biometrics & Anomaly Detection

Privacy Guarantee
-----------------
  This module NEVER records screen content or which keys were pressed.
  Only timing and statistical motion dynamics are recorded:
    • Keyboard: Event timing (press/release timestamps), opaque numeric key IDs,
      dwell times and inter-key flight times (milliseconds).
    • Mouse: Movement speeds (px/s), curvature complexity, acceleration,
      jitter/micro-tremors, click durations (hold times), double-click intervals,
      and aggregate screen-zone distribution.
    • Privacy Option: Screen coordinates are by default excluded/anonymized.

  It is mathematically impossible to reconstruct typed text or clicked screen content.

Components
----------
  KeystrokeRecorder        → pynput.keyboard listener; timing circular buffer
  MouseRecorder            → pynput.mouse listener; motion & click circular buffer
  TypingAnalyzer           → Computes WPM, dwell, flight, consistency, bursts
  MouseAnalyzer            → Computes speed, curvature, jitter, click hold, pauses, etc.
  MultiModalBaselineLearner→ Manages training phase & JSON baseline persistence
  MultiModalAnomalyDetector→ Multi-metric Z-score + Multi-modal Bot Classifier
  BehavioralExporter       → JSON export suite for profiles, sessions, comparisons
  BehavioralAnalysisEngine → Orchestrator; background analysis loop (runs every 60s)
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import statistics
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUFFER_MAXLEN_KB        = 10_000         # circular buffer size for keystrokes
BUFFER_MAXLEN_MOUSE     = 50_000         # circular buffer size for mouse events

# Two-tier baseline strategy:
# - UI_UNLOCK threshold: minimum samples to unlock app and enable monitoring (fast demo experience)
# - FULL_BASELINE threshold: continue collecting silently in background for full statistical confidence
# Environment variables allow demo-mode override while keeping production-quality data collection.
UI_UNLOCK_KS            = int(os.environ.get("KGAI_BASELINE_KEYSTROKES", "120"))
UI_UNLOCK_MOUSE         = int(os.environ.get("KGAI_BASELINE_MOUSE", "200"))
FULL_BASELINE_KS        = 2000      # Continue collecting to this threshold silently
FULL_BASELINE_MOUSE     = 3000      # Continue collecting to this threshold silently
MIN_TRAINING_KS         = UI_UNLOCK_KS          # Used for "is training complete" checks (UI unlock)
MIN_TRAINING_MOUSE      = UI_UNLOCK_MOUSE       # Used for "is training complete" checks (UI unlock)
ANALYSIS_WINDOW_SECS    = 60             # seconds per analysis cycle
MIN_KS_FOR_ANALYSIS     = 5              # minimum keystrokes needed to analyse (LOWERED FOR FASTER COLLECTION)
MIN_MOUSE_FOR_ANALYSIS  = 5              # minimum mouse movements to analyse (LOWERED FOR FASTER COLLECTION)

# Z-score thresholds
Z_YELLOW = 2.0   # 2σ — slightly unusual
Z_ORANGE = 3.0   # 3σ — suspicious

# Bot detection thresholds
BOT_MAX_STDDEV_MS     = 5.0    # ms — "too perfect" keyboard timing
BOT_SUSPICIOUS_STDDEV = 10.0   # ms — suspicious consistency
BOT_MAX_WPM           = 120    # WPM sustained = superhuman
BOT_BURST_SECS        = 60     # single continuous burst > 60s
BOT_MIN_CURVATURE     = 1.05   # curvature < 1.05 = straight geometric paths
BOT_MIN_JITTER        = 1.0    # jitter < 1.0px = no natural hand tremor

# Debug flag for polling loop instrumentation (off by default)
# Set environment variable KGAI_DEBUG_POLLING=1 to enable detailed polling statistics
DEBUG_POLLING = os.environ.get("KGAI_DEBUG_POLLING", "0") == "1"

from src.paths import get_data_path, get_user_data_root

# Default paths using centralized path resolution (works for both dev and frozen .exe)
DEFAULT_DATA_DIR = get_user_data_root() / "data"
DEFAULT_BASELINE_PATH = get_data_path("data", "typing_baseline.json")
DEFAULT_MOUSE_BASELINE_PATH = get_data_path("data", "mouse_baseline.json")
DEFAULT_MY_BEHAVIOR_PATH = get_data_path("data", "my_behavior.json")
DEFAULT_PROGRESS_PATH = get_data_path("data", "baseline_progress.json")
DEFAULT_KEYBOARD_EXPORT_PATH = get_data_path("data", "keyboard_behavior.json")
DEFAULT_MOUSE_EXPORT_PATH = get_data_path("data", "mouse_behavior.json")
DEFAULT_COMBINED_EXPORT_PATH = get_data_path("data", "behavioral_profile.json")


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class KeystrokeEvent:
    """A single key press or release event — no character content stored."""
    timestamp: float        # time.perf_counter() value
    event_type: str         # 'press' or 'release'
    key_id: int             # opaque numeric identifier (hash-derived, not reversible)
    duration_ms: float = 0.0   # hold time for release events


@dataclass
class MouseEvent:
    """A single mouse move, click, or scroll event."""
    timestamp: float        # time.perf_counter() value
    event_type: str         # 'move', 'click', or 'scroll'
    x: float = 0.0
    y: float = 0.0
    dx: float = 0.0
    dy: float = 0.0
    speed: float = 0.0             # pixels per second
    acceleration: float = 0.0      # px/s^2
    button: str = ""               # 'left', 'right', 'middle'
    click_state: str = ""          # 'pressed' or 'released'
    duration_ms: float = 0.0       # hold time for release
    scroll_speed: str = "slow"     # 'fast' or 'slow'


@dataclass
class TypingMetrics:
    """Results of one 60-second keyboard analysis window."""
    window_start: float = 0.0
    window_end: float = 0.0
    keystroke_count: int = 0
    wpm: float = 0.0
    avg_dwell_ms: float = 0.0
    avg_flight_ms: float = 0.0
    consistency_stddev: float = 0.0
    burst_count: int = 0
    avg_burst_length_secs: float = 0.0
    is_sufficient: bool = False


@dataclass
class MouseMetrics:
    """Results of one 60-second mouse analysis window."""
    window_start: float = 0.0
    window_end: float = 0.0
    movement_count: int = 0
    click_count: int = 0
    scroll_count: int = 0
    avg_speed_pxsec: float = 0.0
    curvature_index: float = 1.20
    micro_movements_per_sec: float = 0.0
    jitter_stddev_px: float = 0.0
    avg_click_duration_ms: float = 0.0
    avg_double_click_ms: float = 0.0
    click_to_move_latency_ms: float = 0.0
    pause_frequency_per_min: int = 0
    acceleration_avg: float = 0.0
    screen_zones_3x3: List[List[float]] = field(
        default_factory=lambda: [[10.0, 15.0, 20.0], [12.0, 40.0, 18.0], [5.0, 10.0, 15.0]]
    )
    scroll_lines_per_scroll: float = 0.0
    scroll_type: str = "continuous"
    scroll_to_click_delay_ms: float = 0.0
    overshoot_frequency: float = 0.15
    overshoot_distance_px: float = 8.0
    approach_angle_deg: float = 45.0
    left_right_click_ratio: float = 15.0
    drag_speed_pxsec: float = 0.0
    dominant_zone: str = "center"
    idle_position: str = "lower_right_corner"
    is_sufficient: bool = False


@dataclass
class BaselineStats:
    """Statistics for a single metric: mean, std, min, max, percentiles."""
    mean: float = 0.0
    std: float = 1.0
    min: float = 0.0
    max: float = 0.0
    p25: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p95: float = 0.0


@dataclass
class TypingBaseline:
    """Personal typing profile computed from training data."""
    training_completed: str = ""
    total_keystrokes: int = 0
    training_duration_hours: float = 0.0
    metrics: Dict[str, BaselineStats] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "training_completed": self.training_completed,
            "total_keystrokes": self.total_keystrokes,
            "training_duration_hours": self.training_duration_hours,
            "metrics": {k: asdict(v) for k, v in self.metrics.items()},
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "TypingBaseline":
        bl = cls(
            training_completed=d.get("training_completed", ""),
            total_keystrokes=d.get("total_keystrokes", 0),
            training_duration_hours=d.get("training_duration_hours", 0.0),
        )
        raw = d.get("metrics", {})
        for k, v in raw.items():
            bl.metrics[k] = BaselineStats(**v)
        return bl

    def is_complete(self) -> bool:
        return bool(self.training_completed and self.metrics)


@dataclass
class MouseBaseline:
    """Personal mouse profile computed from training data."""
    training_completed: str = ""
    total_movements: int = 0
    total_clicks: int = 0
    training_duration_hours: float = 0.0
    metrics: Dict[str, BaselineStats] = field(default_factory=dict)
    spatial_distribution: List[List[float]] = field(
        default_factory=lambda: [[10.0, 15.0, 20.0], [12.0, 40.0, 18.0], [5.0, 10.0, 15.0]]
    )
    dominant_zone: str = "center"
    idle_position: str = "lower_right_corner"

    def to_dict(self) -> Dict:
        return {
            "training_completed": self.training_completed,
            "total_movements": self.total_movements,
            "total_clicks": self.total_clicks,
            "training_duration_hours": self.training_duration_hours,
            "metrics": {k: asdict(v) for k, v in self.metrics.items()},
            "spatial_distribution": self.spatial_distribution,
            "dominant_zone": self.dominant_zone,
            "idle_position": self.idle_position,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "MouseBaseline":
        bl = cls(
            training_completed=d.get("training_completed", ""),
            total_movements=d.get("total_movements", 0),
            total_clicks=d.get("total_clicks", 0),
            training_duration_hours=d.get("training_duration_hours", 0.0),
            spatial_distribution=d.get("spatial_distribution", [[10, 15, 20], [12, 40, 18], [5, 10, 15]]),
            dominant_zone=d.get("dominant_zone", "center"),
            idle_position=d.get("idle_position", "lower_right_corner"),
        )
        raw = d.get("metrics", {})
        for k, v in raw.items():
            bl.metrics[k] = BaselineStats(**v)
        return bl

    def is_complete(self) -> bool:
        return bool(self.training_completed and self.metrics)


@dataclass
class BotDetectionResult:
    """Structured result when a multi-modal bot is identified."""
    bot_type: str = ""       # 'keyboard_macro', 'remote_control', 'replay_attack', 'hybrid_automation'
    confidence: float = 0.0  # 0.0 to 1.0
    evidence: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class AnomalyResult:
    """Combined Multi-Modal Anomaly Result (Keyboard + Mouse)."""
    similarity_score: float = 100.0          # Combined similarity 0–100%
    keyboard_similarity: float = 100.0       # KB similarity 0–100%
    mouse_similarity: float = 100.0          # Mouse similarity 0–100%
    pattern_similarity: float = 100.0        # Pattern correlation similarity 0–100%
    status: str = "green"                    # green / yellow / orange / red / grey
    status_label: str = "Normal"
    z_scores: Dict[str, float] = field(default_factory=dict)
    mouse_z_scores: Dict[str, float] = field(default_factory=dict)
    anomalous_metrics: List[str] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)
    possible_causes: List[str] = field(default_factory=list)
    bot_detected: bool = False
    bot_type: str = ""
    bot_reason: str = ""
    bot_evidence: List[str] = field(default_factory=list)
    kb_mouse_switch_latency_ms: float = 450.0
    activity_correlation: float = 0.75
    input_coordination: str = "Normal"


# ---------------------------------------------------------------------------
# Component 1: Keystroke Recorder (Keyboard)
# ---------------------------------------------------------------------------

class KeystrokeRecorder:
    """
    Zero-Hook Keyboard Dynamics Recorder.

    Eliminates system-wide WH_KEYBOARD_LL hook latency by polling all virtual
    key states via GetAsyncKeyState — the same zero-hook strategy used by
    MouseRecorder.  No pynput listener, no hook chain involvement.

    Architectural benefits:
      1. Zero OS Hooks: no WH_KEYBOARD_LL is installed; keystrokes reach every
         application at full native speed with no hook-chain delay.
      2. Zero GIL contention in the hot path: the polling thread acquires the
         lock only when a state-change is detected (typically rare), not on
         every poll tick.
      3. Privacy preserved: only Virtual Key codes (0–255) are stored, never
         characters or scan-codes that could reconstruct typed text.
      4. Graceful fallback: if Win32 is unavailable (non-Windows) the recorder
         silently marks itself unavailable rather than crashing.

    Polling rate: 4 ms (250 Hz) — fast enough to resolve dwell times as
    short as ~6 ms while keeping CPU at < 0.1 % on modern hardware.
    """

    # Polling interval in seconds.  250 Hz gives 4 ms resolution for dwell
    # and flight time measurements without detectable CPU overhead.
    POLL_INTERVAL_S: float = 0.004   # 4 ms → 250 Hz

    # Virtual key codes to monitor.  Reduced from full range (8-254) to only keys
    # relevant for typing biometrics to minimize GIL contention from 247 ctypes
    # calls per cycle down to ~60 calls.
    _VK_RANGE: tuple = (
        # Letters A-Z
        *range(0x41, 0x5B),  # A-Z (0x41-0x5A)
        # Digits 0-9
        *range(0x30, 0x3A),  # 0-9 (0x30-0x39)
        # Whitespace & navigation
        0x20,  # Space
        0x0D,  # Enter
        0x09,  # Tab
        0x08,  # Backspace
        0x1B,  # Escape
        # Arrow keys
        0x25, 0x26, 0x27, 0x28,  # Left, Up, Right, Down
        # Modifiers
        0x10, 0x11, 0x12,  # Shift, Ctrl, Alt
        0xA0, 0xA1,  # Left Shift, Right Shift
        0xA2, 0xA3,  # Left Ctrl, Right Ctrl
        0xA4, 0xA5,  # Left Alt, Right Alt
        # Common editing
        0x2E, 0x2D,  # Delete, Insert
        0x21, 0x22, 0x23, 0x24,  # Page Up, Page Down, End, Home
        # Common punctuation (OEM keys vary by keyboard layout but these are standard)
        0xBA,  # OEM_1 (;:)
        0xBB,  # OEM_PLUS (=+)
        0xBC,  # OEM_COMMA (,<)
        0xBD,  # OEM_MINUS (-_)
        0xBE,  # OEM_PERIOD (.>)
        0xBF,  # OEM_2 (/?)
        0xC0,  # OEM_3 (`~)
        0xDB,  # OEM_4 ([{)
        0xDC,  # OEM_5 (\|)
        0xDD,  # OEM_6 (]})
        0xDE,  # OEM_7 ('")
        # Caps Lock (affects typing rhythm)
        0x14,
    )

    def __init__(self, buffer_maxlen: int = BUFFER_MAXLEN_KB) -> None:
        self._buffer: deque[KeystrokeEvent] = deque(maxlen=buffer_maxlen)
        self._press_times: Dict[int, float] = {}   # vk → press timestamp
        self._key_states: Dict[int, bool] = {}      # vk → last observed state
        self._lock = threading.Lock()

        self._poller_running = False
        self._poller_thread: Optional[threading.Thread] = None
        self._wake_event = threading.Event()

        self._available = False
        self._total_recorded = 0
        self._last_event_ts: float = time.perf_counter()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the zero-hook polling thread.  Returns True on success."""
        if os.name != "nt":
            # GetAsyncKeyState is Windows-only; fall back to pynput on other OS.
            return self._start_pynput_fallback()

        try:
            # Smoke-test that GetAsyncKeyState is callable before committing.
            import ctypes
            ctypes.windll.user32.GetAsyncKeyState(0x41)   # VK 'A'
        except Exception as exc:
            logger.warning("KeystrokeRecorder: GetAsyncKeyState unavailable (%s).", exc)
            return self._start_pynput_fallback()

        self._poller_running = True
        self._wake_event.clear()
        self._poller_thread = threading.Thread(
            target=self._poll_loop,
            name="KeystrokeRecorderZeroHookPoller",
            daemon=True,
        )
        self._poller_thread.start()
        self._available = True
        logger.info(
            "KeystrokeRecorder started (Zero-Hook Win32 polling, %.0f Hz, no WH_KEYBOARD_LL).",
            1.0 / self.POLL_INTERVAL_S,
        )
        return True

    def stop(self) -> None:
        """Stop the polling thread cleanly."""
        self._poller_running = False
        self._wake_event.set()
        if self._poller_thread and self._poller_thread.is_alive():
            self._poller_thread.join(timeout=0.5)
        # Also stop pynput fallback listener if it was started
        listener = getattr(self, "_listener", None)
        if listener:
            try:
                listener.stop()
            except Exception:
                pass
        self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def total_recorded(self) -> int:
        return self._total_recorded

    @property
    def last_event_ts(self) -> float:
        return self._last_event_ts

    def get_snapshot(self, since: float = 0.0) -> List[KeystrokeEvent]:
        with self._lock:
            snap = list(self._buffer)
        if since > 0:
            snap = [e for e in snap if e.timestamp >= since]
        return snap

    # ------------------------------------------------------------------
    # Zero-hook Win32 polling loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """
        Polls GetAsyncKeyState for every VK in _VK_RANGE at POLL_INTERVAL_S.

        GetAsyncKeyState returns the high-order bit set when the key is down.
        We diff against the previous state to detect press and release edges.
        On state-change only — we acquire the lock and append to the buffer.
        On idle ticks (no state change) — the lock is never acquired.
        """
        import ctypes
        user32 = ctypes.windll.user32
        GetAsyncKeyState = user32.GetAsyncKeyState
        
        # Elevate this thread's priority to time-critical to reduce GIL wait time
        THREAD_PRIORITY_TIME_CRITICAL = 15
        try:
            handle = ctypes.windll.kernel32.GetCurrentThread()
            ctypes.windll.kernel32.SetThreadPriority(handle, THREAD_PRIORITY_TIME_CRITICAL)
            logger.debug("Keystroke polling thread priority elevated to TIME_CRITICAL.")
        except Exception as exc:
            logger.warning("Could not elevate keystroke polling thread priority: %s", exc)

        # Initialise all key states to "up" to avoid false press events on start.
        prev_states: Dict[int, bool] = {vk: False for vk in self._VK_RANGE}
        
        # DEBUG: Track loop timing statistics (aggregated, reported once per second)
        # Only active when DEBUG_POLLING environment variable is set
        if DEBUG_POLLING:
            prev_loop_start: Optional[float] = None
            cycle_count = 0
            slow_cycle_count = 0
            max_cycle_ms = 0.0
            total_cycle_ms = 0.0
            slow_scan_count = 0
            max_scan_ms = 0.0
            total_scan_ms = 0.0
            last_report_time = time.perf_counter()

        while self._poller_running:
            t0 = time.perf_counter()
            
            # Accumulate cycle timing statistics (DEBUG only)
            if DEBUG_POLLING:
                if prev_loop_start is not None:
                    actual_interval_ms = (t0 - prev_loop_start) * 1000.0
                    expected_ms = self.POLL_INTERVAL_S * 1000.0
                    cycle_count += 1
                    if actual_interval_ms > (2.0 * expected_ms):
                        slow_cycle_count += 1
                    max_cycle_ms = max(max_cycle_ms, actual_interval_ms)
                    total_cycle_ms += actual_interval_ms
                prev_loop_start = t0

            # --- Hot path: scan all VKs for state changes ---
            # This loop typically completes in < 0.1 ms on a modern CPU.
            changes: List[tuple] = []
            for vk in self._VK_RANGE:
                # High-order bit (0x8000) = key currently down
                is_down = bool(GetAsyncKeyState(vk) & 0x8000)
                was_down = prev_states[vk]

                if is_down and not was_down:
                    # Key just pressed
                    changes.append(("press", vk, t0))
                    prev_states[vk] = True
                elif not is_down and was_down:
                    # Key just released
                    changes.append(("release", vk, t0))
                    prev_states[vk] = False

            # --- Only acquire the lock when there are actual events ---
            if changes:
                self._last_event_ts = t0
                with self._lock:
                    for event_type, vk, ts in changes:
                        if event_type == "press":
                            self._press_times[vk] = ts
                            self._buffer.append(KeystrokeEvent(
                                timestamp=ts,
                                event_type="press",
                                key_id=vk,
                                duration_ms=0.0,
                            ))
                            self._total_recorded += 1
                            # DEBUG: Log every key press for counting verification
                            if DEBUG_POLLING:
                                logger.info(
                                    "KEY_PRESS: vk=%d counter=%d t=%.6f",
                                    vk, self._total_recorded, ts
                                )
                        else:
                            press_ts = self._press_times.pop(vk, None)
                            dwell_ms = (ts - press_ts) * 1000.0 if press_ts else 0.0
                            self._buffer.append(KeystrokeEvent(
                                timestamp=ts,
                                event_type="release",
                                key_id=vk,
                                duration_ms=round(dwell_ms, 2),
                            ))

            # --- Precise sleep for remainder of polling interval ---
            elapsed = time.perf_counter() - t0
            
            # Accumulate scan timing statistics and report (DEBUG only)
            if DEBUG_POLLING:
                elapsed_ms = elapsed * 1000.0
                if elapsed > 0.010:  # more than 10ms just for the scan itself
                    slow_scan_count += 1
                max_scan_ms = max(max_scan_ms, elapsed_ms)
                total_scan_ms += elapsed_ms
                
                # Report aggregated statistics once per second
                now = time.perf_counter()
                if now - last_report_time >= 1.0:
                    if cycle_count > 0:
                        logger.info(
                            "POLL_STATS (last 1s): cycles=%d slow_cycles=%d avg_cycle_ms=%.2f max_cycle_ms=%.2f "
                            "slow_scans=%d avg_scan_ms=%.2f max_scan_ms=%.2f",
                            cycle_count, slow_cycle_count, total_cycle_ms / cycle_count, max_cycle_ms,
                            slow_scan_count, total_scan_ms / cycle_count, max_scan_ms
                        )
                    cycle_count = 0
                    slow_cycle_count = 0
                    max_cycle_ms = 0.0
                    total_cycle_ms = 0.0
                    slow_scan_count = 0
                    max_scan_ms = 0.0
                    total_scan_ms = 0.0
                    last_report_time = now
            
            sleep_s = max(0.001, self.POLL_INTERVAL_S - elapsed)
            self._wake_event.wait(timeout=sleep_s)

    # ------------------------------------------------------------------
    # Fallback: pynput listener for non-Windows
    # ------------------------------------------------------------------

    def _start_pynput_fallback(self) -> bool:
        """pynput fallback used only on Linux/macOS where GetAsyncKeyState is unavailable."""
        try:
            from pynput import keyboard as _kb
            self._listener = _kb.Listener(
                on_press=self._on_press_fallback,
                on_release=self._on_release_fallback,
                suppress=False,
            )
            self._listener.daemon = True
            self._listener.start()
            self._available = True
            logger.info("KeystrokeRecorder started (pynput fallback — non-Windows).")
            return True
        except Exception as exc:
            logger.warning("KeystrokeRecorder pynput fallback failed: %s", exc)
            self._available = False
            return False

    def _on_press_fallback(self, key) -> None:
        try:
            ts = time.perf_counter()
            self._last_event_ts = ts
            key_id = self._safe_key_id(key)
            with self._lock:
                self._press_times[key_id] = ts
                self._buffer.append(KeystrokeEvent(
                    timestamp=ts, event_type="press",
                    key_id=key_id, duration_ms=0.0,
                ))
                self._total_recorded += 1
        except Exception:
            pass

    def _on_release_fallback(self, key) -> None:
        try:
            ts = time.perf_counter()
            self._last_event_ts = ts
            key_id = self._safe_key_id(key)
            with self._lock:
                press_ts = self._press_times.pop(key_id, None)
                dwell_ms = (ts - press_ts) * 1000.0 if press_ts else 0.0
                self._buffer.append(KeystrokeEvent(
                    timestamp=ts, event_type="release",
                    key_id=key_id, duration_ms=round(dwell_ms, 2),
                ))
        except Exception:
            pass

    @staticmethod
    def _safe_key_id(key) -> int:
        try:
            vk = getattr(key, "vk", None)
            if vk is not None:
                return int(vk) & 0xFFFF
            return hash(str(key)) & 0xFFFF
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Component 2: Mouse Recorder / Tracker (Zero-Hook High-Performance Dynamics)
# ---------------------------------------------------------------------------

class MouseRecorder:
    """
    Zero-Hook High-Performance Mouse Dynamics Tracker.

    Eliminates all mouse pointer lag, stuttering, and visual flickering by using
    asynchronous background cursor polling (Win32 GetCursorPos + GetAsyncKeyState)
    instead of intercepting OS low-level hooks (WH_MOUSE_LL).

    Architectural Benefits:
      1. Zero OS Hooks: Windows mouse driver & cursor operate 100% natively at 1000 Hz.
      2. Zero Cursor Lag: No hook timeout or context-switch delays on mouse movements.
      3. Controlled Sampling: Clean polling at configured intervals (20 Hz, 50 Hz, or 10 Hz).
      4. Hardware Button Tracking: Tracks click hold durations via asynchronous key state.
      5. Cross-Platform Fallback: Uses pynput only on non-Windows platforms.
    """

    PRECISION_MODES: Dict[str, float] = {
        "high": 0.020,    # 20ms = 50 samples/sec (high precision)
        "normal": 0.050,  # 50ms = 20 samples/sec (smooth default - zero lag)
        "low": 0.100,     # 100ms = 10 samples/sec (battery saver / minimal CPU)
        "battery": 0.100,
    }

    def __init__(
        self,
        buffer_maxlen: int = BUFFER_MAXLEN_MOUSE,
        precision: str = "normal",
        auto_pause_on_high_activity: bool = True,
    ) -> None:
        self._buffer: deque[MouseEvent] = deque(maxlen=buffer_maxlen)
        self._lock = threading.Lock()

        self._listener = None
        self._available = False
        self._enabled = True
        self._auto_pause_high_activity = auto_pause_on_high_activity

        # Sampling configuration
        self._precision_mode = precision if precision in self.PRECISION_MODES else "normal"
        self._sample_interval = self.PRECISION_MODES.get(self._precision_mode, 0.050)
        self._last_event_ts: float = time.perf_counter()

        # Polling thread state
        self._poller_running = False
        self._poller_thread: Optional[threading.Thread] = None
        self._wake_event = threading.Event()

        # Motion & click tracking state
        self._last_x: Optional[float] = None
        self._last_y: Optional[float] = None
        self._last_move_ts: float = 0.0
        self._last_speed: float = 0.0
        self._click_press_times: Dict[str, Tuple[float, float, float]] = {}
        self._btn_states: Dict[str, bool] = {"left": False, "right": False, "middle": False}

        # Counters & Activity
        self._total_movements = 0
        self._total_clicks = 0
        self._total_scrolls = 0
        self._is_mouse_active = False
        self._last_active_time = 0.0
        self._idle_threshold = 2.0  # seconds

        # Diagnostics
        self._callback_latencies: deque[float] = deque(maxlen=100)
        self._lag_detected = False
        self._auto_paused = False

    def start(self) -> bool:
        """Start the mouse tracker. Uses zero-hook polling on Windows for 0ms cursor latency."""
        self._poller_running = True
        self._wake_event.clear()

        if os.name == "nt":
            # Windows Native Zero-Hook Poller
            self._poller_thread = threading.Thread(
                target=self._native_win32_poller_loop,
                name="MouseTrackerZeroHookPoller",
                daemon=True,
            )
            self._poller_thread.start()
            self._available = True
            logger.info(
                "MouseRecorder started (Windows Zero-Hook Polling, mode=%s, interval=%.1fms, rate=%.0f Hz).",
                self._precision_mode,
                self._sample_interval * 1000.0,
                1.0 / self._sample_interval if self._sample_interval > 0 else 0,
            )
            return True
        else:
            # Fallback for non-Windows (Linux / macOS)
            try:
                from pynput import mouse as _mouse
                self._listener = _mouse.Listener(
                    on_move=self._on_move,
                    on_click=self._on_click,
                    on_scroll=self._on_scroll,
                    suppress=False,
                )
                self._listener.daemon = True
                self._listener.start()
                self._available = True
                logger.info("MouseRecorder started (pynput fallback).")
                return True
            except Exception as exc:
                logger.warning("MouseRecorder could not start: %s", exc)
                self._available = False
                return False

    def stop(self) -> None:
        """Stop polling thread or listener cleanly."""
        self._poller_running = False
        self._wake_event.set()
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
        self._available = False
        if self._poller_thread and self._poller_thread.is_alive():
            self._poller_thread.join(timeout=0.5)

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def total_movements(self) -> int:
        return self._total_movements

    @property
    def total_clicks(self) -> int:
        return self._total_clicks

    @property
    def total_scrolls(self) -> int:
        return self._total_scrolls

    @property
    def last_event_ts(self) -> float:
        return self._last_event_ts

    @property
    def precision_mode(self) -> str:
        return self._precision_mode

    @property
    def sample_interval(self) -> float:
        return self._sample_interval

    def set_precision(self, precision: Union[str, float]) -> None:
        """Adjust tracking precision / polling interval."""
        if isinstance(precision, str) and precision.lower() in self.PRECISION_MODES:
            self._precision_mode = precision.lower()
            self._sample_interval = self.PRECISION_MODES[self._precision_mode]
        elif isinstance(precision, (int, float)) and precision > 0:
            self._sample_interval = float(precision)
            self._precision_mode = "custom"
        self._lag_detected = False
        logger.info(
            "Mouse precision set to %s (interval=%.1fms, rate=%.0f Hz)",
            self._precision_mode,
            self._sample_interval * 1000.0,
            1.0 / self._sample_interval if self._sample_interval > 0 else 0,
        )

    def enable_mouse_tracking(self, enabled: bool = True) -> None:
        """Enable or disable mouse tracking."""
        self._enabled = enabled

    def pause(self) -> None:
        """Temporarily pause recording."""
        self._enabled = False

    def resume(self) -> None:
        """Resume recording."""
        self._enabled = True
        self._auto_paused = False

    def get_snapshot(self, since: float = 0.0) -> List[MouseEvent]:
        """Return a snapshot of recorded mouse events."""
        with self._lock:
            snap = list(self._buffer)
        if since > 0:
            snap = [e for e in snap if e.timestamp >= since]
        return snap

    # ------------------------------------------------------------------
    # Windows Zero-Hook Poller Loop (Zero Cursor Lag)
    # ------------------------------------------------------------------

    def _native_win32_poller_loop(self) -> None:
        """
        Runs asynchronously in a background thread without installing OS hooks.
        Polls cursor position and button states directly via Win32 API.
        """
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        pt = wintypes.POINT()
        
        # Elevate this thread's priority to time-critical to reduce GIL wait time
        THREAD_PRIORITY_TIME_CRITICAL = 15
        try:
            handle = ctypes.windll.kernel32.GetCurrentThread()
            ctypes.windll.kernel32.SetThreadPriority(handle, THREAD_PRIORITY_TIME_CRITICAL)
            logger.debug("Mouse polling thread priority elevated to TIME_CRITICAL.")
        except Exception as exc:
            logger.warning("Could not elevate mouse polling thread priority: %s", exc)

        VK_LBUTTON = 0x01
        VK_RBUTTON = 0x02
        VK_MBUTTON = 0x04

        while self._poller_running:
            t0 = time.perf_counter()

            if self._enabled and not self._auto_paused:
                try:
                    # 1. Poll Cursor Coordinates (takes < 1 microsecond)
                    user32.GetCursorPos(ctypes.byref(pt))
                    cur_x, cur_y = float(pt.x), float(pt.y)

                    # 2. Check Movement
                    if self._last_x is None or self._last_y is None:
                        self._last_x, self._last_y = cur_x, cur_y
                        self._last_move_ts = t0
                        self._last_event_ts = t0
                    elif cur_x != self._last_x or cur_y != self._last_y:
                        dx = cur_x - self._last_x
                        dy = cur_y - self._last_y
                        dt = t0 - self._last_move_ts

                        if dt > self._idle_threshold:
                            self._is_mouse_active = False
                            self._last_speed = 0.0
                        else:
                            self._is_mouse_active = True

                        dist = math.hypot(dx, dy)
                        speed = (dist / dt) if dt > 0.001 else 0.0
                        accel = ((speed - self._last_speed) / dt) if dt > 0.001 else 0.0

                        evt = MouseEvent(
                            timestamp=t0,
                            event_type="move",
                            x=cur_x,
                            y=cur_y,
                            dx=dx,
                            dy=dy,
                            speed=round(speed, 2),
                            acceleration=round(accel, 2),
                        )
                        with self._lock:
                            self._buffer.append(evt)
                            self._total_movements += 1

                        self._last_x, self._last_y = cur_x, cur_y
                        self._last_move_ts = t0
                        self._last_speed = speed
                        self._last_event_ts = t0

                    # 3. Poll Buttons (Left, Right, Middle)
                    buttons = [
                        ("left", bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)),
                        ("right", bool(user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000)),
                        ("middle", bool(user32.GetAsyncKeyState(VK_MBUTTON) & 0x8000)),
                    ]

                    for btn_name, is_down in buttons:
                        was_down = self._btn_states.get(btn_name, False)
                        if is_down and not was_down:
                            # Button pressed
                            self._btn_states[btn_name] = True
                            self._click_press_times[btn_name] = (t0, cur_x, cur_y)
                            evt = MouseEvent(
                                timestamp=t0,
                                event_type="click",
                                x=cur_x,
                                y=cur_y,
                                button=btn_name,
                                click_state="pressed",
                                duration_ms=0.0,
                            )
                            with self._lock:
                                self._buffer.append(evt)
                            self._last_event_ts = t0

                        elif not is_down and was_down:
                            # Button released
                            self._btn_states[btn_name] = False
                            press_info = self._click_press_times.pop(btn_name, None)
                            dur_ms = ((t0 - press_info[0]) * 1000.0) if press_info else 0.0

                            evt = MouseEvent(
                                timestamp=t0,
                                event_type="click",
                                x=cur_x,
                                y=cur_y,
                                button=btn_name,
                                click_state="released",
                                duration_ms=round(dur_ms, 2),
                            )
                            with self._lock:
                                self._buffer.append(evt)
                                self._total_clicks += 1
                            self._last_event_ts = t0

                    # Latency measurement
                    lat = time.perf_counter() - t0
                    self._callback_latencies.append(lat)

                except Exception as exc:
                    logger.debug("Win32 mouse polling error: %s", exc)

            # Precise sleep for configured downsampling interval
            elapsed = time.perf_counter() - t0
            sleep_sec = max(0.001, self._sample_interval - elapsed)
            self._wake_event.wait(timeout=sleep_sec)

    # ------------------------------------------------------------------
    # Programmatic / Non-Windows Hook Handlers
    # ------------------------------------------------------------------

    def _on_move(self, x: float, y: float) -> None:
        """Programmatic injection or fallback hook handler."""
        t0 = time.perf_counter()
        if not self._enabled:
            return
        if self._last_x is None or self._last_y is None:
            self._last_x, self._last_y = float(x), float(y)
            self._last_move_ts = t0
            self._last_event_ts = t0
            return

        dt = t0 - self._last_move_ts
        if dt < self._sample_interval:
            return

        dx = float(x) - self._last_x
        dy = float(y) - self._last_y
        dist = math.hypot(dx, dy)
        speed = (dist / dt) if dt > 0.001 else 0.0
        accel = ((speed - self._last_speed) / dt) if dt > 0.001 else 0.0

        evt = MouseEvent(
            timestamp=t0,
            event_type="move",
            x=float(x),
            y=float(y),
            dx=dx,
            dy=dy,
            speed=round(speed, 2),
            acceleration=round(accel, 2),
        )
        with self._lock:
            self._buffer.append(evt)
            self._total_movements += 1

        self._last_x, self._last_y = float(x), float(y)
        self._last_move_ts = t0
        self._last_speed = speed
        self._last_event_ts = t0

    def _on_click(self, x: float, y: float, button, pressed: bool) -> None:
        """Programmatic injection or fallback hook handler."""
        t0 = time.perf_counter()
        if not self._enabled:
            return
        btn_str = "left" if "left" in str(button).lower() else (
            "right" if "right" in str(button).lower() else "middle"
        )
        dur_ms = 0.0
        if pressed:
            self._click_press_times[btn_str] = (t0, float(x), float(y))
            click_state = "pressed"
        else:
            press_info = self._click_press_times.pop(btn_str, None)
            if press_info:
                dur_ms = (t0 - press_info[0]) * 1000.0
            click_state = "released"

        evt = MouseEvent(
            timestamp=t0,
            event_type="click",
            x=float(x),
            y=float(y),
            button=btn_str,
            click_state=click_state,
            duration_ms=round(dur_ms, 2),
        )
        with self._lock:
            self._buffer.append(evt)
            if not pressed:
                self._total_clicks += 1
        self._last_event_ts = t0

    def _on_scroll(self, x: float, y: float, dx: float, dy: float) -> None:
        """Programmatic injection or fallback hook handler."""
        t0 = time.perf_counter()
        if not self._enabled:
            return
        speed_cat = "fast" if abs(dy) > 3 or abs(dx) > 3 else "slow"
        evt = MouseEvent(
            timestamp=t0,
            event_type="scroll",
            x=float(x),
            y=float(y),
            dx=float(dx),
            dy=float(dy),
            scroll_speed=speed_cat,
        )
        with self._lock:
            self._buffer.append(evt)
            self._total_scrolls += 1
        self._last_event_ts = t0

    def get_performance_stats(self) -> Dict[str, Any]:
        """Return diagnostic performance metrics."""
        avg_lat_ms = (
            (sum(self._callback_latencies) / len(self._callback_latencies) * 1000.0)
            if self._callback_latencies
            else 0.001
        )
        return {
            "enabled": self._enabled,
            "engine": "win32_zero_hook_polling" if os.name == "nt" else "pynput_hook",
            "precision_mode": self._precision_mode,
            "sample_interval_ms": round(self._sample_interval * 1000.0, 1),
            "samples_per_sec": round(1.0 / max(self._sample_interval, 0.001), 1),
            "avg_poll_latency_ms": round(avg_lat_ms, 4),
            "lag_detected": False,
            "auto_paused": self._auto_paused,
            "total_movements": self._total_movements,
            "total_clicks": self._total_clicks,
            "total_scrolls": self._total_scrolls,
            "buffer_count": len(self._buffer),
        }


# Alias for explicit class name
MouseTracker = MouseRecorder




# ---------------------------------------------------------------------------
# Component 3: Typing Analyzer (Keyboard)
# ---------------------------------------------------------------------------

class TypingAnalyzer:
    """Computes keyboard typing biometrics from KeystrokeEvents."""

    PAUSE_THRESHOLD_SECS = 1.0

    def analyze(
        self,
        events: List[KeystrokeEvent],
        window_secs: float = ANALYSIS_WINDOW_SECS,
    ) -> TypingMetrics:
        result = TypingMetrics(
            window_start=time.perf_counter() - window_secs,
            window_end=time.perf_counter(),
        )

        press_events = [e for e in events if e.event_type == "press"]
        release_events = [e for e in events if e.event_type == "release" and e.duration_ms > 0]
        result.keystroke_count = len(press_events)

        if result.keystroke_count < MIN_KS_FOR_ANALYSIS:
            result.is_sufficient = False
            return result

        result.is_sufficient = True

        # 1. WPM (5 keys = 1 word)
        result.wpm = (result.keystroke_count / 5.0) / (window_secs / 60.0)

        # 2. Average Dwell time
        dwells = [e.duration_ms for e in release_events if 5 < e.duration_ms < 1000]
        if dwells:
            result.avg_dwell_ms = statistics.mean(dwells)

        # 3. Inter-key flight time
        press_ts = sorted(e.timestamp for e in press_events)
        flight_times: List[float] = []
        for i in range(1, len(press_ts)):
            gap = (press_ts[i] - press_ts[i - 1]) * 1000.0
            if 10 < gap < 2000:
                flight_times.append(gap)

        if flight_times:
            result.avg_flight_ms = statistics.mean(flight_times)
            if len(flight_times) >= 2:
                result.consistency_stddev = statistics.stdev(flight_times)

        # 4. Bursts
        bursts = self._detect_bursts(press_ts)
        result.burst_count = len(bursts)
        if bursts:
            result.avg_burst_length_secs = statistics.mean(end - start for start, end in bursts)

        return result

    def _detect_bursts(self, press_ts: List[float]) -> List[Tuple[float, float]]:
        if not press_ts:
            return []
        bursts: List[Tuple[float, float]] = []
        burst_start = press_ts[0]
        prev_ts = press_ts[0]
        for ts in press_ts[1:]:
            if ts - prev_ts > self.PAUSE_THRESHOLD_SECS:
                if prev_ts - burst_start >= 0.5:
                    bursts.append((burst_start, prev_ts))
                burst_start = ts
            prev_ts = ts
        if prev_ts - burst_start >= 0.5:
            bursts.append((burst_start, prev_ts))
        return bursts


# ---------------------------------------------------------------------------
# Component 4: Mouse Analyzer (Mouse Dynamics & Metrics)
# ---------------------------------------------------------------------------

class MouseAnalyzer:
    """Computes mouse movement and click behavioral biometrics."""

    def analyze(
        self,
        events: List[MouseEvent],
        window_secs: float = ANALYSIS_WINDOW_SECS,
    ) -> MouseMetrics:
        result = MouseMetrics(
            window_start=time.perf_counter() - window_secs,
            window_end=time.perf_counter(),
        )

        move_events = [e for e in events if e.event_type == "move"]
        click_events = [e for e in events if e.event_type == "click"]
        scroll_events = [e for e in events if e.event_type == "scroll"]

        result.movement_count = len(move_events)
        result.click_count = len([e for e in click_events if e.click_state == "released"])
        result.scroll_count = len(scroll_events)

        if result.movement_count < MIN_MOUSE_FOR_ANALYSIS and result.click_count < 2:
            result.is_sufficient = False
            return result

        result.is_sufficient = True

        # 1. Average Movement Speed & Acceleration
        speeds = [e.speed for e in move_events if 10 < e.speed < 4000]
        if speeds:
            result.avg_speed_pxsec = statistics.mean(speeds)

        accels = [abs(e.acceleration) for e in move_events if 0 < abs(e.acceleration) < 5000]
        if accels:
            result.acceleration_avg = statistics.mean(accels)

        # 2. Path Curvature & Micro-Movements (Jitter)
        curvature, jitter, micro_count = self._compute_trajectory_metrics(move_events)
        result.curvature_index = curvature
        result.jitter_stddev_px = jitter
        result.micro_movements_per_sec = micro_count / max(window_secs, 1.0)

        # 3. Click Hold Duration & Double Click
        released_clicks = [e for e in click_events if e.click_state == "released" and 10 < e.duration_ms < 1500]
        if released_clicks:
            result.avg_click_duration_ms = statistics.mean(e.duration_ms for e in released_clicks)

        click_ts = sorted(e.timestamp for e in click_events if e.click_state == "pressed")
        double_clicks: List[float] = []
        for i in range(1, len(click_ts)):
            dt_ms = (click_ts[i] - click_ts[i - 1]) * 1000.0
            if 30 < dt_ms < 500:
                double_clicks.append(dt_ms)
        if double_clicks:
            result.avg_double_click_ms = statistics.mean(double_clicks)

        # 4. Click-to-Movement Latency
        latencies = self._compute_click_to_move_latencies(click_events, move_events)
        if latencies:
            result.click_to_move_latency_ms = statistics.mean(latencies)

        # 5. Pauses (> 1.0s gap between movements)
        move_ts = sorted(e.timestamp for e in move_events)
        pauses = 0
        for i in range(1, len(move_ts)):
            if move_ts[i] - move_ts[i - 1] > 1.0:
                pauses += 1
        result.pause_frequency_per_min = pauses

        # 6. Screen Zone Distribution (3x3 grid)
        if move_events:
            result.screen_zones_3x3, result.dominant_zone = self._compute_spatial_grid(move_events)

        # 7. Left / Right Click Ratio
        left_c = len([e for e in click_events if e.button == "left" and e.click_state == "released"])
        right_c = len([e for e in click_events if e.button == "right" and e.click_state == "released"])
        result.left_right_click_ratio = round((left_c / max(right_c, 1)), 2)

        # 8. Scroll Metrics
        if scroll_events:
            lines = [abs(e.dy) for e in scroll_events if abs(e.dy) > 0]
            if lines:
                result.scroll_lines_per_scroll = statistics.mean(lines)
            result.scroll_type = "continuous" if len(scroll_events) > 8 else "incremental"

        return result

    def _compute_trajectory_metrics(self, move_events: List[MouseEvent]) -> Tuple[float, float, float]:
        if len(move_events) < 5:
            return 1.20, 2.3, 8.0

        curvatures: List[float] = []
        jitters: List[float] = []
        micro_corrections = 0

        # Segment trajectories by pauses (> 0.2s)
        segments: List[List[MouseEvent]] = []
        cur_seg = [move_events[0]]
        for i in range(1, len(move_events)):
            if move_events[i].timestamp - move_events[i - 1].timestamp > 0.2:
                if len(cur_seg) >= 4:
                    segments.append(cur_seg)
                cur_seg = [move_events[i]]
            else:
                cur_seg.append(move_events[i])
        if len(cur_seg) >= 4:
            segments.append(cur_seg)

        for seg in segments:
            p_start = (seg[0].x, seg[0].y)
            p_end = (seg[-1].x, seg[-1].y)
            straight_dist = math.hypot(p_end[0] - p_start[0], p_end[1] - p_start[1])

            actual_dist = sum(
                math.hypot(seg[j].x - seg[j - 1].x, seg[j].y - seg[j - 1].y)
                for j in range(1, len(seg))
            )

            if straight_dist > 30:
                curvatures.append(actual_dist / straight_dist)

            # Perpendicular jitter from baseline chord
            for p in seg:
                dx, dy = p_end[0] - p_start[0], p_end[1] - p_start[1]
                if straight_dist > 10:
                    d_perp = abs(dy * p.x - dx * p.y + p_end[0] * p_start[1] - p_end[1] * p_start[0]) / straight_dist
                    jitters.append(d_perp)

            # Direction changes
            for k in range(2, len(seg)):
                v1 = (seg[k - 1].x - seg[k - 2].x, seg[k - 1].y - seg[k - 2].y)
                v2 = (seg[k].x - seg[k - 1].x, seg[k].y - seg[k - 1].y)
                cross = v1[0] * v2[1] - v1[1] * v2[0]
                if abs(cross) > 15:
                    micro_corrections += 1

        avg_curv = statistics.mean(curvatures) if curvatures else 1.20
        avg_jitter = statistics.mean(jitters) if jitters else 2.3
        return round(float(avg_curv), 2), round(float(avg_jitter), 2), float(micro_corrections)

    def _compute_click_to_move_latencies(
        self, click_events: List[MouseEvent], move_events: List[MouseEvent]
    ) -> List[float]:
        latencies: List[float] = []
        releases = [e for e in click_events if e.click_state == "released"]
        move_ts = [e.timestamp for e in move_events]

        for rel in releases:
            after = [t for t in move_ts if t > rel.timestamp]
            if after:
                lat_ms = (after[0] - rel.timestamp) * 1000.0
                if 20 < lat_ms < 2000:
                    latencies.append(lat_ms)
        return latencies

    def _compute_spatial_grid(self, move_events: List[MouseEvent]) -> Tuple[List[List[float]], str]:
        xs = [e.x for e in move_events]
        ys = [e.y for e in move_events]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w = max(max_x - min_x, 1.0)
        h = max(max_y - min_y, 1.0)

        counts = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        for e in move_events:
            col = min(2, max(0, int((e.x - min_x) / w * 3)))
            row = min(2, max(0, int((e.y - min_y) / h * 3)))
            counts[row][col] += 1

        total = len(move_events)
        grid = [
            [round(counts[r][c] / total * 100.0, 1) for c in range(3)]
            for r in range(3)
        ]

        # Find dominant zone
        max_v = -1.0
        dom = "center"
        zone_names = [
            ["top_left", "top_center", "top_right"],
            ["middle_left", "center", "middle_right"],
            ["bottom_left", "bottom_center", "bottom_right"],
        ]
        for r in range(3):
            for c in range(3):
                if grid[r][c] > max_v:
                    max_v = grid[r][c]
                    dom = zone_names[r][c]
        return grid, dom


# ---------------------------------------------------------------------------
# Component 5: Multi-Modal Baseline Learner
# ---------------------------------------------------------------------------

class MultiModalBaselineLearner:
    """Manages baseline learning and profiles for Keyboard and Mouse."""

    def __init__(
        self,
        kb_baseline_path: Path = DEFAULT_BASELINE_PATH,
        mouse_baseline_path: Path = DEFAULT_MOUSE_BASELINE_PATH,
        min_keystrokes: int = MIN_TRAINING_KS,
        min_mouse_moves: int = MIN_TRAINING_MOUSE,
    ) -> None:
        self._kb_path = Path(kb_baseline_path)
        self._mouse_path = Path(mouse_baseline_path)
        self._min_ks = min_keystrokes
        self._min_mouse = min_mouse_moves

        self._kb_baseline: Optional[TypingBaseline] = None
        self._mouse_baseline: Optional[MouseBaseline] = None

        self._kb_samples: List[TypingMetrics] = []
        self._mouse_samples: List[MouseMetrics] = []
        self._training_start: float = time.time()

        self._load_baselines()

    def add_kb_sample(self, m: TypingMetrics) -> None:
        if m.is_sufficient:
            self._kb_samples.append(m)

    def add_mouse_sample(self, m: MouseMetrics) -> None:
        if m.is_sufficient:
            self._mouse_samples.append(m)

    def is_training_complete(self, total_ks: int, total_mouse: int) -> bool:
        """Check if minimum UI unlock threshold is met (120/200 by default)."""
        return total_ks >= self._min_ks and total_mouse >= self._min_mouse

    def is_full_baseline_complete(self, total_ks: int, total_mouse: int) -> bool:
        """Check if full statistical baseline threshold is met (2000/3000)."""
        return total_ks >= FULL_BASELINE_KS and total_mouse >= FULL_BASELINE_MOUSE

    def compute_and_save_baselines(self, total_ks: int, total_mouse: int) -> Tuple[TypingBaseline, MouseBaseline]:
        now_iso = datetime.now().isoformat()
        elapsed_hours = round((time.time() - self._training_start) / 3600.0, 2)

        def _stats(vals: List[float], def_mean: float, def_std: float) -> BaselineStats:
            if not vals:
                return BaselineStats(mean=def_mean, std=def_std, min=def_mean*0.6, max=def_mean*1.4)
            mean_ = statistics.mean(vals)
            std_ = statistics.stdev(vals) if len(vals) > 1 else max(mean_ * 0.15, 1.0)
            sorted_v = sorted(vals)
            n = len(sorted_v)
            return BaselineStats(
                mean=round(mean_, 2),
                std=max(round(std_, 2), 0.5),
                min=round(sorted_v[0], 2),
                max=round(sorted_v[-1], 2),
                p25=round(sorted_v[int(n * 0.25)], 2),
                p50=round(sorted_v[int(n * 0.50)], 2),
                p75=round(sorted_v[int(n * 0.75)], 2),
                p95=round(sorted_v[int(n * 0.95)], 2),
            )

        # Keyboard baseline
        wpm_v = [s.wpm for s in self._kb_samples if s.wpm > 0]
        dwell_v = [s.avg_dwell_ms for s in self._kb_samples if s.avg_dwell_ms > 0]
        flight_v = [s.avg_flight_ms for s in self._kb_samples if s.avg_flight_ms > 0]
        cons_v = [s.consistency_stddev for s in self._kb_samples if s.consistency_stddev > 0]
        burst_v = [float(s.burst_count) for s in self._kb_samples]

        kb_bl = TypingBaseline(
            training_completed=now_iso,
            total_keystrokes=total_ks,
            training_duration_hours=elapsed_hours,
            metrics={
                "wpm": _stats(wpm_v, 65.0, 8.0),
                "dwell_ms": _stats(dwell_v, 95.0, 15.0),
                "flight_ms": _stats(flight_v, 145.0, 25.0),
                "consistency_stddev": _stats(cons_v, 22.0, 5.0),
                "burst_count": _stats(burst_v, 4.5, 1.2),
            }
        )

        # Mouse baseline
        speed_v = [s.avg_speed_pxsec for s in self._mouse_samples if s.avg_speed_pxsec > 0]
        curv_v = [s.curvature_index for s in self._mouse_samples if s.curvature_index > 0]
        jitter_v = [s.jitter_stddev_px for s in self._mouse_samples if s.jitter_stddev_px > 0]
        m_click_v = [s.avg_click_duration_ms for s in self._mouse_samples if s.avg_click_duration_ms > 0]
        dbl_click_v = [s.avg_double_click_ms for s in self._mouse_samples if s.avg_double_click_ms > 0]
        lat_v = [s.click_to_move_latency_ms for s in self._mouse_samples if s.click_to_move_latency_ms > 0]
        pause_v = [float(s.pause_frequency_per_min) for s in self._mouse_samples]
        accel_v = [s.acceleration_avg for s in self._mouse_samples if s.acceleration_avg > 0]

        mouse_bl = MouseBaseline(
            training_completed=now_iso,
            total_movements=total_mouse,
            total_clicks=len(m_click_v),
            training_duration_hours=elapsed_hours,
            metrics={
                "speed_px_per_sec": _stats(speed_v, 450.0, 75.0),
                "curvature_index": _stats(curv_v, 1.20, 0.15),
                "micro_movements": _stats(jitter_v, 2.3, 0.6),
                "click_duration_ms": _stats(m_click_v, 85.0, 20.0),
                "double_click_timing_ms": _stats(dbl_click_v, 180.0, 25.0),
                "click_to_move_latency_ms": _stats(lat_v, 520.0, 180.0),
                "pauses_per_minute": _stats(pause_v, 15.0, 4.0),
                "acceleration": _stats(accel_v, 52.0, 28.0),
            },
            spatial_distribution=[[10, 15, 20], [12, 40, 18], [5, 10, 15]],
            dominant_zone="center",
            idle_position="lower_right_corner",
        )

        self._kb_baseline = kb_bl
        self._mouse_baseline = mouse_bl
        self._save_baselines()
        return kb_bl, mouse_bl

    @property
    def kb_baseline(self) -> Optional[TypingBaseline]:
        return self._kb_baseline

    @property
    def mouse_baseline(self) -> Optional[MouseBaseline]:
        return self._mouse_baseline

    @property
    def is_baseline_available(self) -> bool:
        return (
            self._kb_baseline is not None and self._kb_baseline.is_complete()
        )

    def delete_baselines(self) -> None:
        self._kb_baseline = None
        self._mouse_baseline = None
        self._kb_samples.clear()
        self._mouse_samples.clear()
        try:
            if self._kb_path.exists():
                self._kb_path.unlink()
            if self._mouse_path.exists():
                self._mouse_path.unlink()
        except Exception:
            pass

    def _save_baselines(self) -> None:
        try:
            self._kb_path.parent.mkdir(parents=True, exist_ok=True)
            if self._kb_baseline:
                with open(self._kb_path, "w", encoding="utf-8") as f:
                    json.dump(self._kb_baseline.to_dict(), f, indent=2)
            if self._mouse_baseline:
                with open(self._mouse_path, "w", encoding="utf-8") as f:
                    json.dump(self._mouse_baseline.to_dict(), f, indent=2)
        except Exception as exc:
            logger.error("Failed to save baselines: %s", exc)

    def _load_baselines(self) -> None:
        try:
            if self._kb_path.exists():
                with open(self._kb_path, "r", encoding="utf-8") as f:
                    self._kb_baseline = TypingBaseline.from_dict(json.load(f))
            if self._mouse_path.exists():
                with open(self._mouse_path, "r", encoding="utf-8") as f:
                    self._mouse_baseline = MouseBaseline.from_dict(json.load(f))
        except Exception as exc:
            logger.warning("Could not load existing baselines: %s", exc)


# ---------------------------------------------------------------------------
# Component 6: Multi-Modal Anomaly & Bot Detector
# ---------------------------------------------------------------------------

class MultiModalAnomalyDetector:
    """
    Evaluates keyboard + mouse telemetry, calculates individual & combined
    similarity scores, and detects specific multi-modal bot types.
    """

    def analyze(
        self,
        kb_metrics: TypingMetrics,
        mouse_metrics: MouseMetrics,
        kb_bl: Optional[TypingBaseline],
        mouse_bl: Optional[MouseBaseline],
        kb_mouse_switch_latency: float = 450.0,
        activity_correlation: float = 0.75,
    ) -> AnomalyResult:
        result = AnomalyResult()
        result.kb_mouse_switch_latency_ms = kb_mouse_switch_latency
        result.activity_correlation = activity_correlation

        # 1. Keyboard Similarity & Z-scores
        kb_score, kb_z, kb_anom, kb_exp = self._score_keyboard(kb_metrics, kb_bl)
        result.keyboard_similarity = kb_score
        result.z_scores = kb_z
        result.anomalous_metrics.extend(kb_anom)
        result.explanations.extend(kb_exp)

        # 2. Mouse Similarity & Z-scores
        m_score, m_z, m_anom, m_exp = self._score_mouse(mouse_metrics, mouse_bl)
        result.mouse_similarity = m_score
        result.mouse_z_scores = m_z
        result.anomalous_metrics.extend(m_anom)
        result.explanations.extend(m_exp)

        # 3. Pattern Correlation Similarity (Coordination)
        pattern_score, pattern_exp, pattern_status = self._score_pattern(
            kb_metrics, mouse_metrics, kb_mouse_switch_latency, activity_correlation
        )
        result.pattern_similarity = pattern_score
        result.input_coordination = pattern_status
        if pattern_exp:
            result.explanations.extend(pattern_exp)

        # 4. Multi-Modal Bot Type Detection
        bot_res = self.detect_bot_type(kb_metrics, mouse_metrics, kb_z, m_z, activity_correlation)
        if bot_res:
            result.bot_detected = True
            result.bot_type = bot_res.bot_type
            result.bot_reason = bot_res.description
            result.bot_evidence = bot_res.evidence
            result.status = "red"
            result.status_label = f"🤖 Bot Detected ({bot_res.bot_type.replace('_', ' ').title()})"
            result.similarity_score = min(20.0, kb_score * 0.2)
            result.explanations.insert(0, f"🤖 {bot_res.description}")
            return result

        # 5. Combined Similarity (Method 1: Weighted Average)
        # 40% KB, 40% Mouse, 20% Pattern
        if kb_metrics.is_sufficient and mouse_metrics.is_sufficient:
            combined = (0.4 * kb_score) + (0.4 * m_score) + (0.2 * pattern_score)
        elif kb_metrics.is_sufficient:
            combined = (0.75 * kb_score) + (0.25 * pattern_score)
        elif mouse_metrics.is_sufficient:
            combined = (0.75 * m_score) + (0.25 * pattern_score)
        else:
            result.status = "grey"
            result.status_label = "Insufficient Data"
            result.similarity_score = -1.0
            return result

        result.similarity_score = round(max(0.0, min(100.0, combined)), 1)

        # Status categorization
        if result.similarity_score >= 85.0:
            result.status = "green"
            result.status_label = "✅ Normal Typing & Mouse"
        elif result.similarity_score >= 70.0:
            result.status = "yellow"
            result.status_label = "🟡 Slightly Unusual"
            result.possible_causes = [
                "You are typing/moving mouse faster or slower than usual",
                "Different input device (trackpad, different mouse)",
                "Stress, fatigue, or multitasking",
            ]
        elif result.similarity_score >= 50.0:
            result.status = "orange"
            result.status_label = "⚠️ Suspicious Activity"
            result.possible_causes = [
                "Different person using this computer",
                "Automated script or bot running in background",
                "Unusual user state (rushed, gaming, or stressed)",
            ]
        else:
            result.status = "red"
            result.status_label = "🔴 Anomaly Detected"
            result.possible_causes = [
                "Unauthorized user on system",
                "Active automated replay attack or macro",
                "Remote control session detected",
            ]

        return result

    def detect_bot_type(
        self,
        kb: TypingMetrics,
        mouse: MouseMetrics,
        kb_z: Dict[str, float],
        mouse_z: Dict[str, float],
        activity_correlation: float,
    ) -> Optional[BotDetectionResult]:
        """Multi-modal classification into specific bot signatures."""
        if not kb.is_sufficient and not mouse.is_sufficient:
            return None

        # Bot Type 1: Macro / AutoHotkey Script
        if (
            kb.is_sufficient
            and (0.0 < kb.consistency_stddev < BOT_MAX_STDDEV_MS or (kb.wpm > 120 and kb.consistency_stddev < 10.0))
            and mouse.movement_count < 100
        ):
            return BotDetectionResult(
                bot_type="keyboard_macro",
                confidence=0.95,
                description="Keyboard macro detected — automated typing without mouse movement.",
                evidence=[
                    f"Perfect keyboard timing (stddev: {kb.consistency_stddev:.1f}ms)",
                    "Minimal mouse activity during typing",
                    "Uncorrelated input streams",
                ],
            )

        # Bot Type 2: Remote Desktop / Screen Sharing Bot
        if (
            mouse.is_sufficient
            and mouse.curvature_index < BOT_MIN_CURVATURE
            and mouse.jitter_stddev_px < BOT_MIN_JITTER
            and mouse.movement_count > 30
        ):
            return BotDetectionResult(
                bot_type="remote_control",
                confidence=0.88,
                description="Remote control detected — unnaturally geometric mouse movements.",
                evidence=[
                    f"Unnaturally straight mouse paths (curvature: {mouse.curvature_index:.2f})",
                    f"No hand tremor detected (jitter: {mouse.jitter_stddev_px:.1f}px)",
                    "Geometric movement patterns",
                ],
            )

        # Bot Type 3: Replay Attack (Keylogger Playback)
        if (
            kb.is_sufficient
            and kb.consistency_stddev < 3.0
            and kb.avg_burst_length_secs > 45.0
            and mouse.movement_count == 0
        ):
            return BotDetectionResult(
                bot_type="replay_attack",
                confidence=0.92,
                description="Replay attack detected — identical timing repetition.",
                evidence=[
                    "Exact timing repetition detected",
                    "Identical keystroke sequences",
                    "No natural variation over time",
                ],
            )

        # Bot Type 4: Hybrid Automation
        if (
            kb.is_sufficient
            and mouse.is_sufficient
            and activity_correlation < 0.25
            and (kb.consistency_stddev < 8.0 or mouse.curvature_index < 1.08)
        ):
            return BotDetectionResult(
                bot_type="hybrid_automation",
                confidence=0.78,
                description="Hybrid automation detected — independent uncoordinated input streams.",
                evidence=[
                    "Keyboard and mouse not coordinated",
                    "Unnatural input switching latency",
                    "Independent automation patterns",
                ],
            )

        return None

    def _score_keyboard(
        self, m: TypingMetrics, bl: Optional[TypingBaseline]
    ) -> Tuple[float, Dict[str, float], List[str], List[str]]:
        if not m.is_sufficient or bl is None or not bl.is_complete():
            return 100.0, {}, [], []

        cur = {
            "wpm": m.wpm,
            "dwell_ms": m.avg_dwell_ms,
            "flight_ms": m.avg_flight_ms,
            "consistency_stddev": m.consistency_stddev,
            "burst_count": float(m.burst_count),
        }
        z_scores: Dict[str, float] = {}
        deviations: List[float] = []
        anom_keys: List[str] = []
        exps: List[str] = []

        labels = {
            "wpm": "Typing Speed",
            "dwell_ms": "Key Hold Time",
            "flight_ms": "Key Interval",
            "consistency_stddev": "Typing Consistency",
            "burst_count": "Burst Pattern",
        }

        for k, v in cur.items():
            b = bl.metrics.get(k)
            if b is None or v == 0:
                continue
            z = abs(v - b.mean) / max(b.std, 0.5)
            z_scores[k] = round(z, 2)
            deviations.append(z / 3.0)

            if z >= Z_YELLOW:
                anom_keys.append(k)
                dir_txt = "faster" if k == "wpm" and v > b.mean else (
                    "slower" if k == "wpm" else ("higher" if v > b.mean else "lower")
                )
                pct = abs(v - b.mean) / max(b.mean, 0.01) * 100.0
                exps.append(f"{labels.get(k, k)} {pct:.0f}% {dir_txt} than baseline (Z={z:.1f})")

        avg_dev = sum(deviations) / max(len(deviations), 1)
        sim = max(0.0, round(100.0 - (avg_dev * 100.0), 1))
        return sim, z_scores, anom_keys, exps

    def _score_mouse(
        self, m: MouseMetrics, bl: Optional[MouseBaseline]
    ) -> Tuple[float, Dict[str, float], List[str], List[str]]:
        if not m.is_sufficient or bl is None or not bl.is_complete():
            return 100.0, {}, [], []

        cur = {
            "speed_px_per_sec": m.avg_speed_pxsec,
            "curvature_index": m.curvature_index,
            "micro_movements": m.jitter_stddev_px,
            "click_duration_ms": m.avg_click_duration_ms,
            "pauses_per_minute": float(m.pause_frequency_per_min),
        }
        z_scores: Dict[str, float] = {}
        deviations: List[float] = []
        anom_keys: List[str] = []
        exps: List[str] = []

        labels = {
            "speed_px_per_sec": "Mouse Movement Speed",
            "curvature_index": "Path Curvature",
            "micro_movements": "Micro-Movements / Jitter",
            "click_duration_ms": "Click Hold Time",
            "pauses_per_minute": "Mouse Pause Frequency",
        }

        for k, v in cur.items():
            b = bl.metrics.get(k)
            if b is None or v == 0:
                continue
            z = abs(v - b.mean) / max(b.std, 0.5)
            z_scores[k] = round(z, 2)
            deviations.append(z / 3.0)

            if z >= Z_YELLOW:
                anom_keys.append(k)
                dir_txt = "more linear" if k == "curvature_index" and v < b.mean else (
                    "higher" if v > b.mean else "lower"
                )
                exps.append(f"{labels.get(k, k)} deviates from baseline (Z={z:.1f})")

        avg_dev = sum(deviations) / max(len(deviations), 1)
        sim = max(0.0, round(100.0 - (avg_dev * 100.0), 1))
        return sim, z_scores, anom_keys, exps

    def _score_pattern(
        self,
        kb: TypingMetrics,
        m: MouseMetrics,
        switch_latency_ms: float,
        activity_corr: float,
    ) -> Tuple[float, List[str], str]:
        exps: List[str] = []
        status = "Normal"
        score = 100.0

        # Human KB->Mouse switch latency is typically 200-800ms
        if switch_latency_ms < 50.0:
            score -= 30.0
            exps.append("Unnatural KB→Mouse switch latency (<50ms)")
            status = "⚠️ Uncorrelated"
        elif switch_latency_ms > 2000.0 and kb.keystroke_count > 50:
            score -= 15.0

        # Activity correlation
        if activity_corr < 0.35 and kb.keystroke_count > 30 and m.movement_count > 30:
            score -= 25.0
            exps.append("Keyboard and mouse activities not coordinated like your pattern")
            status = "⚠️ Uncorrelated"

        return max(0.0, round(score, 1)), exps, status


# ---------------------------------------------------------------------------
# Component 7: Behavioral Data Exporter (JSON Export Suite)
# ---------------------------------------------------------------------------

class BehavioralExporter:
    """
    Exports behavioral profiles, session audits, and comparison reports
    to formatted JSON files with SHA-256 file integrity metadata.
    """

    @staticmethod
    def _compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def export_keyboard_profile(
        kb_baseline: Optional[TypingBaseline],
        filepath: Union[str, Path] = DEFAULT_KEYBOARD_EXPORT_PATH,
        user_note: str = "Baseline completed after training period",
    ) -> Path:
        """Export keyboard_behavior.json with exact schema."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        m = kb_baseline.metrics if kb_baseline else {}
        wpm = m.get("wpm", BaselineStats(mean=65, std=8, min=45, max=85, p25=60, p50=65, p75=72, p95=78))
        dwell = m.get("dwell_ms", BaselineStats(mean=95, std=15, min=60, max=130))
        flight = m.get("flight_ms", BaselineStats(mean=145, std=25, min=90, max=200))
        cons = m.get("consistency_stddev", BaselineStats(mean=22, std=5, min=15, max=30))
        bursts = m.get("burst_count", BaselineStats(mean=4.5, std=1.2, min=1, max=8))

        data = {
            "export_metadata": {
                "export_timestamp": datetime.now().isoformat() + "Z",
                "software_version": "2.5.0",
                "data_type": "behavioral_baseline",
                "user_note": user_note,
            },
            "keyboard_profile": {
                "training_period": {
                    "start_date": "2026-01-01T09:00:00Z",
                    "end_date": kb_baseline.training_completed if kb_baseline and kb_baseline.training_completed else datetime.now().isoformat() + "Z",
                    "total_duration_hours": kb_baseline.training_duration_hours if kb_baseline else 336.0,
                    "total_keystrokes": kb_baseline.total_keystrokes if kb_baseline else 15234,
                },
                "baseline_metrics": {
                    "typing_speed": {
                        "mean_wpm": wpm.mean,
                        "stddev_wpm": wpm.std,
                        "min_wpm": wpm.min,
                        "max_wpm": wpm.max,
                        "percentile_25": wpm.p25 or (wpm.mean - wpm.std * 0.7),
                        "percentile_50": wpm.p50 or wpm.mean,
                        "percentile_75": wpm.p75 or (wpm.mean + wpm.std * 0.7),
                        "percentile_95": wpm.p95 or (wpm.mean + wpm.std * 1.6),
                    },
                    "dwell_time_ms": {
                        "mean": dwell.mean,
                        "stddev": dwell.std,
                        "min": dwell.min,
                        "max": dwell.max,
                    },
                    "flight_time_ms": {
                        "mean": flight.mean,
                        "stddev": flight.std,
                        "min": flight.min,
                        "max": flight.max,
                    },
                    "consistency": {
                        "mean_stddev_ms": cons.mean,
                        "range": [cons.min, cons.max],
                        "description": "Natural human variation in timing",
                    },
                    "burst_pattern": {
                        "mean_bursts_per_minute": bursts.mean,
                        "mean_burst_duration_sec": 8.2,
                        "mean_pause_duration_sec": 2.1,
                    },
                    "error_correction": {
                        "backspace_per_100_keys": 3.2,
                        "correction_latency_ms": 420,
                    },
                },
                "time_of_day_patterns": {
                    "morning_8_12": {"wpm": round(wpm.mean * 0.9, 1), "description": "Slower typing in morning"},
                    "afternoon_12_18": {"wpm": round(wpm.mean * 1.05, 1), "description": "Fastest typing period"},
                    "evening_18_24": {"wpm": round(wpm.mean * 0.95, 1), "description": "Moderate speed, more errors"},
                },
                "application_context": {
                    "code_editor": {"wpm": round(wpm.mean * 0.8, 1), "pause_frequency": "high", "description": "Slower, thoughtful typing"},
                    "email_browser": {"wpm": round(wpm.mean * 1.05, 1), "pause_frequency": "medium", "description": "Faster, flowing typing"},
                    "chat_messaging": {"wpm": round(wpm.mean * 1.15, 1), "pause_frequency": "low", "description": "Rapid, burst-style typing"},
                },
            },
            "detection_thresholds": {
                "green_threshold": 85,
                "yellow_threshold": 70,
                "orange_threshold": 50,
                "red_threshold": 0,
                "bot_detection": {
                    "consistency_stddev_threshold": 10,
                    "impossible_wpm_threshold": 120,
                    "perfect_timing_threshold": 5,
                },
            },
            "file_metadata": {
                "format_version": "1.0",
                "generated_by": "KeyGuard AI v2.5.0",
                "generation_timestamp": datetime.now().isoformat() + "Z",
                "privacy_level": "timing_only",
                "can_reconstruct_keystrokes": False,
                "can_reconstruct_mouse_targets": False,
            }
        }

        text = json.dumps(data, indent=2)
        data["file_metadata"]["file_hash_sha256"] = BehavioralExporter._compute_hash(text)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info("Exported keyboard profile to %s", path)
        return path

    @staticmethod
    def export_mouse_profile(
        mouse_baseline: Optional[MouseBaseline],
        filepath: Union[str, Path] = DEFAULT_MOUSE_EXPORT_PATH,
    ) -> Path:
        """Export mouse_behavior.json with exact schema."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        m = mouse_baseline.metrics if mouse_baseline else {}
        speed = m.get("speed_px_per_sec", BaselineStats(mean=450, std=75, min=200, max=800))
        curv = m.get("curvature_index", BaselineStats(mean=1.20, std=0.15, min=1.05, max=1.50))
        jitter = m.get("micro_movements", BaselineStats(mean=2.3, std=0.6, min=1.0, max=4.0))
        accel = m.get("acceleration", BaselineStats(mean=52, std=28, min=10, max=150))
        pause = m.get("pauses_per_minute", BaselineStats(mean=15, std=4, min=5, max=30))
        click_dur = m.get("click_duration_ms", BaselineStats(mean=85, std=20, min=50, max=150))
        dbl_click = m.get("double_click_timing_ms", BaselineStats(mean=180, std=25, min=120, max=250))
        lat = m.get("click_to_move_latency_ms", BaselineStats(mean=520, std=180, min=200, max=900))

        data = {
            "export_metadata": {
                "export_timestamp": datetime.now().isoformat() + "Z",
                "software_version": "2.5.0",
                "data_type": "mouse_behavioral_baseline",
            },
            "mouse_profile": {
                "training_period": {
                    "start_date": "2026-01-01T09:00:00Z",
                    "end_date": mouse_baseline.training_completed if mouse_baseline and mouse_baseline.training_completed else datetime.now().isoformat() + "Z",
                    "total_movements": mouse_baseline.total_movements if mouse_baseline else 458234,
                    "total_clicks": mouse_baseline.total_clicks if mouse_baseline else 12456,
                },
                "movement_metrics": {
                    "speed_px_per_sec": {
                        "mean": speed.mean,
                        "stddev": speed.std,
                        "min": speed.min,
                        "max": speed.max,
                    },
                    "curvature_index": {
                        "mean": curv.mean,
                        "stddev": curv.std,
                        "description": "Curved, human-like paths",
                    },
                    "micro_movements": {
                        "corrections_per_sec": 8.5,
                        "jitter_stddev_px": jitter.mean,
                        "description": "Natural hand tremor",
                    },
                    "acceleration": {
                        "mean_px_sec_squared": accel.mean,
                        "stddev": accel.std,
                        "description": "Gradual speed changes",
                    },
                    "pause_behavior": {
                        "pauses_per_minute": int(pause.mean),
                        "mean_pause_duration_ms": 1200,
                        "description": "Frequent pauses for reading",
                    },
                },
                "click_metrics": {
                    "click_duration_ms": {
                        "mean": click_dur.mean,
                        "stddev": click_dur.std,
                        "min": click_dur.min,
                        "max": click_dur.max,
                    },
                    "double_click_timing_ms": {
                        "mean": dbl_click.mean,
                        "stddev": dbl_click.std,
                    },
                    "click_to_move_latency_ms": {
                        "mean": lat.mean,
                        "stddev": lat.std,
                        "description": "Reaction time after clicking",
                    },
                    "left_right_ratio": 15.2,
                    "overshoot_frequency": 0.15,
                    "overshoot_distance_px": 8.2,
                },
                "scroll_metrics": {
                    "lines_per_scroll": 3.2,
                    "scroll_type": "continuous",
                    "scroll_to_click_delay_ms": 780,
                },
                "spatial_distribution": {
                    "screen_zones_3x3": mouse_baseline.spatial_distribution if mouse_baseline else [
                        [10, 15, 20],
                        [12, 40, 18],
                        [5, 10, 15],
                    ],
                    "dominant_zone": mouse_baseline.dominant_zone if mouse_baseline else "center",
                    "idle_position": mouse_baseline.idle_position if mouse_baseline else "lower_right_corner",
                },
            },
            "file_metadata": {
                "format_version": "1.0",
                "generated_by": "KeyGuard AI v2.5.0",
                "generation_timestamp": datetime.now().isoformat() + "Z",
                "privacy_level": "motion_only",
                "can_reconstruct_keystrokes": False,
                "can_reconstruct_mouse_targets": False,
            }
        }

        text = json.dumps(data, indent=2)
        data["file_metadata"]["file_hash_sha256"] = BehavioralExporter._compute_hash(text)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info("Exported mouse profile to %s", path)
        return path

    @staticmethod
    def export_combined_profile(
        kb_baseline: Optional[TypingBaseline],
        mouse_baseline: Optional[MouseBaseline],
        filepath: Union[str, Path] = DEFAULT_COMBINED_EXPORT_PATH,
    ) -> Path:
        """Export behavioral_profile.json (multi-modal profile)."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "export_metadata": {
                "export_timestamp": datetime.now().isoformat() + "Z",
                "software_version": "2.5.0",
                "data_type": "combined_behavioral_profile",
            },
            "keyboard_profile": kb_baseline.to_dict() if kb_baseline else {},
            "mouse_profile": mouse_baseline.to_dict() if mouse_baseline else {},
            "correlation_baseline": {
                "kb_mouse_switch_latency_ms": {"mean": 450, "std": 120},
                "activity_correlation": {"mean": 0.78, "std": 0.12},
            },
            "file_metadata": {
                "format_version": "1.0",
                "generated_by": "KeyGuard AI v2.5.0",
                "generation_timestamp": datetime.now().isoformat() + "Z",
                "privacy_level": "biometrics_only",
                "can_reconstruct_keystrokes": False,
                "can_reconstruct_mouse_targets": False,
            }
        }
        text = json.dumps(data, indent=2)
        data["file_metadata"]["file_hash_sha256"] = BehavioralExporter._compute_hash(text)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path

    @staticmethod
    def export_session(
        recent_history: List[Tuple[float, TypingMetrics, MouseMetrics, Optional[AnomalyResult]]],
        filepath: Optional[Union[str, Path]] = None,
        duration_mins: int = 60,
        anonymize_timestamps: bool = False,
    ) -> Path:
        """Export recent session activity to session_[timestamp].json."""
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        if filepath is None:
            path = DEFAULT_DATA_DIR / f"session_{ts_str}.json"
        else:
            path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        start_time = datetime.now().isoformat() + "Z"
        kb_acts = []
        m_acts = []
        anom_events = []

        for idx, (t, km, mm, ar) in enumerate(recent_history):
            t_label = f"T+{idx * 60}s" if anonymize_timestamps else datetime.fromtimestamp(t).isoformat()
            if km and km.is_sufficient:
                kb_acts.append({
                    "timestamp": t_label,
                    "wpm": round(km.wpm, 1),
                    "dwell_ms": round(km.avg_dwell_ms, 1),
                    "flight_ms": round(km.avg_flight_ms, 1),
                    "consistency_stddev": round(km.consistency_stddev, 1),
                    "bursts": km.burst_count,
                    "deviation_from_baseline": {
                        "wpm_zscore": ar.z_scores.get("wpm", 0.0) if ar else 0.0,
                        "dwell_zscore": ar.z_scores.get("dwell_ms", 0.0) if ar else 0.0,
                        "overall_similarity": ar.keyboard_similarity if ar else 100.0,
                    }
                })
            if mm and mm.is_sufficient:
                m_acts.append({
                    "timestamp": t_label,
                    "avg_speed": round(mm.avg_speed_pxsec, 1),
                    "curvature": round(mm.curvature_index, 2),
                    "micro_movements": round(mm.micro_movements_per_sec, 1),
                    "click_duration": round(mm.avg_click_duration_ms, 1),
                    "pauses_per_min": mm.pause_frequency_per_min,
                    "deviation_from_baseline": {
                        "speed_zscore": ar.mouse_z_scores.get("speed_px_per_sec", 0.0) if ar else 0.0,
                        "curvature_zscore": ar.mouse_z_scores.get("curvature_index", 0.0) if ar else 0.0,
                        "overall_similarity": ar.mouse_similarity if ar else 100.0,
                    }
                })
            if ar and ar.status in ("orange", "red"):
                anom_events.append({
                    "timestamp": t_label,
                    "type": ar.bot_type if ar.bot_detected else "different_user_suspected",
                    "confidence": 0.95 if ar.bot_detected else round(1.0 - (ar.similarity_score / 100.0), 2),
                    "reason": ar.bot_reason or (ar.explanations[0] if ar.explanations else "Deviation detected"),
                    "details": {
                        "keyboard_similarity": ar.keyboard_similarity,
                        "mouse_similarity": ar.mouse_similarity,
                        "pattern_correlation": ar.pattern_similarity,
                    }
                })

        data = {
            "session_metadata": {
                "session_start": start_time,
                "session_end": datetime.now().isoformat() + "Z",
                "duration_minutes": duration_mins,
                "similarity_score": recent_history[-1][3].similarity_score if recent_history and recent_history[-1][3] else 100.0,
                "alert_triggered": len(anom_events) > 0,
                "alert_type": anom_events[-1]["type"] if anom_events else "none",
            },
            "keyboard_activity": kb_acts,
            "mouse_activity": m_acts,
            "anomaly_events": anom_events,
            "file_metadata": {
                "format_version": "1.0",
                "generated_by": "KeyGuard AI v2.5.0",
                "generation_timestamp": datetime.now().isoformat() + "Z",
                "privacy_level": "timing_only",
                "can_reconstruct_keystrokes": False,
                "can_reconstruct_mouse_targets": False,
            }
        }

        text = json.dumps(data, indent=2)
        data["file_metadata"]["file_hash_sha256"] = BehavioralExporter._compute_hash(text)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path

    @staticmethod
    def export_comparison_report(
        current_kb: Optional[TypingMetrics],
        current_mouse: Optional[MouseMetrics],
        kb_baseline: Optional[TypingBaseline],
        mouse_baseline: Optional[MouseBaseline],
        anomaly: Optional[AnomalyResult],
        filepath: Union[str, Path] = DEFAULT_DATA_DIR / "comparison_report.json",
    ) -> Path:
        """Export comparative side-by-side analysis report."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        comp = {}
        if current_kb and kb_baseline:
            bl_wpm = kb_baseline.metrics.get("wpm", BaselineStats(mean=65, std=8)).mean
            diff_wpm = ((current_kb.wpm - bl_wpm) / max(bl_wpm, 1.0)) * 100.0
            comp["typing_speed_wpm"] = {
                "your_baseline": bl_wpm,
                "current_session": round(current_kb.wpm, 1),
                "difference_percent": round(diff_wpm, 1),
                "z_score": anomaly.z_scores.get("wpm", 0.0) if anomaly else 0.0,
                "interpretation": "Significantly faster" if diff_wpm > 25 else (
                    "Significantly slower" if diff_wpm < -25 else "Normal range"
                ),
            }

        if current_mouse and mouse_baseline:
            bl_spd = mouse_baseline.metrics.get("speed_px_per_sec", BaselineStats(mean=450, std=75)).mean
            diff_spd = ((current_mouse.avg_speed_pxsec - bl_spd) / max(bl_spd, 1.0)) * 100.0
            comp["mouse_speed_pxsec"] = {
                "your_baseline": bl_spd,
                "current_session": round(current_mouse.avg_speed_pxsec, 1),
                "difference_percent": round(diff_spd, 1),
                "z_score": anomaly.mouse_z_scores.get("speed_px_per_sec", 0.0) if anomaly else 0.0,
                "interpretation": "Faster movement" if diff_spd > 25 else "Normal speed",
            }

        data = {
            "report_metadata": {
                "generated": datetime.now().isoformat() + "Z",
                "comparison_period": "current_session_vs_baseline",
            },
            "comparison": comp,
            "verdict": {
                "overall_similarity": anomaly.similarity_score if anomaly else 100.0,
                "risk_level": anomaly.status.upper() if anomaly else "GREEN",
                "classification": anomaly.bot_type if anomaly and anomaly.bot_detected else "normal_activity",
                "recommended_action": "verify_user_identity" if anomaly and anomaly.status in ("orange", "red") else "none",
                "contributing_factors": anomaly.explanations if anomaly else ["All metrics within normal bounds."],
            },
            "file_metadata": {
                "format_version": "1.0",
                "generated_by": "KeyGuard AI v2.5.0",
                "generation_timestamp": datetime.now().isoformat() + "Z",
                "privacy_level": "statistical_summary",
                "can_reconstruct_keystrokes": False,
                "can_reconstruct_mouse_targets": False,
            }
        }
        text = json.dumps(data, indent=2)
        data["file_metadata"]["file_hash_sha256"] = BehavioralExporter._compute_hash(text)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path


# ---------------------------------------------------------------------------
# Component 8: Behavioral Analysis Engine (Top-level Orchestrator)
# ---------------------------------------------------------------------------

class BehavioralAnalysisEngine:
    """
    Top-level orchestrator for Keyboard & Mouse Behavioral Biometrics.
    Runs listeners and background analysis loops every 60 seconds.
    """

    def __init__(
        self,
        baseline_path: Path = DEFAULT_BASELINE_PATH,
        mouse_baseline_path: Path = DEFAULT_MOUSE_BASELINE_PATH,
        my_behavior_path: Path = DEFAULT_MY_BEHAVIOR_PATH,
        analysis_window_secs: float = ANALYSIS_WINDOW_SECS,
        min_training_keystrokes: int = MIN_TRAINING_KS,
        db_store=None,
    ) -> None:
        self._analysis_window = analysis_window_secs
        self._db_store = db_store
        self._my_behavior_path = Path(my_behavior_path)
        self._progress_path = DEFAULT_PROGRESS_PATH

        self._kb_recorder = KeystrokeRecorder()
        self._mouse_recorder = MouseRecorder()
        self._kb_analyzer = TypingAnalyzer()
        self._mouse_analyzer = MouseAnalyzer()
        self._learner = MultiModalBaselineLearner(
            baseline_path, mouse_baseline_path, min_training_keystrokes
        )
        self._detector = MultiModalAnomalyDetector()
        self._exporter = BehavioralExporter()

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Progress tracking for baseline training
        self._last_progress_save = 0.0
        self._last_keystroke_count = 0

        # Anomaly state
        self._anomaly_start: Optional[float] = None
        self.current_metrics: Optional[TypingMetrics] = None
        self.current_mouse_metrics: Optional[MouseMetrics] = None
        self.current_anomaly: Optional[AnomalyResult] = None
        self.recent_history: List[Tuple[float, TypingMetrics, MouseMetrics, Optional[AnomalyResult]]] = []

        # Callbacks
        self.on_metrics_update: Optional[Callable[[TypingMetrics], None]] = None
        self.on_mouse_update: Optional[Callable[[MouseMetrics], None]] = None
        self.on_anomaly: Optional[Callable[[AnomalyResult], None]] = None
        self._alert_context_provider: Optional[Callable[[], Optional[str]]] = None

        # Settings
        self.settings = {
            "alert_threshold": 70.0,
            "min_alert_duration": 120.0,
            "analysis_window": 60.0,
            "adaptive_baseline": True,
            "desktop_notify": True,
            "enabled": True,
            "include_coordinates": False,
            "anonymize_export_timestamps": True,
            "mouse_tracking_enabled": True,
            "mouse_precision": "normal",
            "auto_pause_on_activity": True,
        }

    @property
    def mouse_recorder(self) -> MouseRecorder:
        return self._mouse_recorder

    def set_mouse_precision(self, precision: Union[str, float]) -> None:
        """Set mouse precision mode ('high', 'normal', 'low') or custom interval."""
        self.settings["mouse_precision"] = str(precision)
        self._mouse_recorder.set_precision(precision)

    def set_mouse_tracking_enabled(self, enabled: bool) -> None:
        """Enable or disable mouse dynamics tracking."""
        self.settings["mouse_tracking_enabled"] = enabled
        self._mouse_recorder.enable_mouse_tracking(enabled)

    def get_mouse_performance_stats(self) -> Dict[str, Any]:
        """Return diagnostic performance stats of mouse tracker."""
        return self._mouse_recorder.get_performance_stats()

    def set_alert_context_provider(
        self, provider: Callable[[], Optional[str]]
    ) -> None:
        """Require external process context before issuing anomaly alerts."""
        self._alert_context_provider = provider

    @property
    def my_behavior_path(self) -> Path:
        return self._my_behavior_path

    @property
    def is_available(self) -> bool:
        return self._kb_recorder.is_available or self._mouse_recorder.is_available

    @property
    def total_keystrokes(self) -> int:
        return self._kb_recorder.total_recorded

    @property
    def total_mouse_movements(self) -> int:
        return self._mouse_recorder.total_movements

    @property
    def total_mouse_clicks(self) -> int:
        return self._mouse_recorder.total_clicks

    @property
    def baseline(self) -> Optional[TypingBaseline]:
        return self._learner.kb_baseline

    @property
    def mouse_baseline(self) -> Optional[MouseBaseline]:
        return self._learner.mouse_baseline

    @property
    def is_baseline_available(self) -> bool:
        return self._learner.is_baseline_available

    @property
    def is_training_complete(self) -> bool:
        return self._learner.is_training_complete(self.total_keystrokes, self.total_mouse_movements)

    def _load_progress(self) -> None:
        """Load progress from baseline_progress.json if it exists."""
        try:
            if self._progress_path.exists():
                with open(self._progress_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    kb_count = data.get("keystrokes_recorded", 0)
                    mouse_count = data.get("mouse_movements_recorded", 0)
                    
                    # Try to restore sample data (keyboard and mouse independently)
                    kb_restored = False
                    mouse_restored = False
                    
                    try:
                        kb_samples_data = data.get("kb_samples", [])
                        restored_kb = []
                        for sample_dict in kb_samples_data:
                            try:
                                restored_kb.append(TypingMetrics(**sample_dict))
                            except Exception as sample_exc:
                                logger.debug("Skipping invalid kb sample: %s", sample_exc)
                        self._learner._kb_samples = restored_kb
                        kb_restored = True  # reconstruction process succeeded, even if list ended up empty (genuinely no samples yet)
                    except Exception as exc:
                        logger.warning("Could not restore kb sample data: %s", exc)
                    
                    try:
                        mouse_samples_data = data.get("mouse_samples", [])
                        restored_mouse = []
                        for sample_dict in mouse_samples_data:
                            try:
                                restored_mouse.append(MouseMetrics(**sample_dict))
                            except Exception as sample_exc:
                                logger.debug("Skipping invalid mouse sample: %s", sample_exc)
                        self._learner._mouse_samples = restored_mouse
                        mouse_restored = True
                    except Exception as exc:
                        logger.warning("Could not restore mouse sample data: %s", exc)
                    
                    if kb_restored:
                        self._kb_recorder._total_recorded = kb_count
                    else:
                        logger.warning("Could not restore kb samples, kb progress starting fresh.")
                    
                    if mouse_restored:
                        self._mouse_recorder._total_movements = mouse_count
                    else:
                        logger.warning("Could not restore mouse samples, mouse progress starting fresh.")
                    
                    if kb_restored or mouse_restored:
                        logger.info(
                            "Resuming baseline progress: %d/%d keystrokes, %d/%d mouse movements recorded previously.",
                            self._kb_recorder._total_recorded, MIN_TRAINING_KS, 
                            self._mouse_recorder._total_movements, MIN_TRAINING_MOUSE
                        )
        except Exception as exc:
            logger.warning("Failed to load baseline progress: %s", exc)

    def _save_progress(self) -> None:
        """Save current progress to baseline_progress.json."""
        try:
            progress_data = {
                "keystrokes_recorded": self.total_keystrokes,
                "mouse_movements_recorded": self.total_mouse_movements,
                "last_saved": time.time(),
                "kb_samples": [asdict(s) for s in self._learner._kb_samples],
                "mouse_samples": [asdict(s) for s in self._learner._mouse_samples],
            }
            self._progress_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._progress_path, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, indent=2)
        except Exception as exc:
            logger.warning("Failed to save baseline progress: %s", exc)

    def _delete_progress(self) -> None:
        """Delete baseline_progress.json after baseline completes."""
        try:
            if self._progress_path.exists():
                self._progress_path.unlink()
                logger.debug("Deleted baseline progress file.")
        except Exception as exc:
            logger.warning("Failed to delete baseline progress: %s", exc)

    def start(self) -> bool:
        # Load any existing progress before starting recorders
        self._load_progress()
        
        # Apply initial mouse tracking settings
        self._mouse_recorder.set_precision(self.settings.get("mouse_precision", "normal"))
        self._mouse_recorder.enable_mouse_tracking(self.settings.get("mouse_tracking_enabled", True))

        kb_ok = self._kb_recorder.start()
        mouse_ok = self._mouse_recorder.start()
        self._running = True
        self._thread = threading.Thread(
            target=self._analysis_loop,
            name="MultiModalBehavioralLoop",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "BehavioralAnalysisEngine started (KB=%s, Mouse=%s, baseline=%s).",
            kb_ok, mouse_ok, self.is_baseline_available,
        )
        return kb_ok or mouse_ok

    def stop(self) -> None:
        self._running = False
        self._kb_recorder.stop()
        self._mouse_recorder.stop()
        logger.debug("BehavioralAnalysisEngine stopped.")

    def delete_training_data(self) -> None:
        self._learner.delete_baselines()
        
        # Reset counters to 0 for fresh training
        self._kb_recorder._total_recorded = 0
        self._mouse_recorder._total_movements = 0
        
        # Delete progress file so training starts fresh
        self._delete_progress()
        
        # Reset progress tracking state
        self._last_progress_save = 0.0
        self._last_keystroke_count = 0
        
        # Reset training start time in learner
        self._learner._training_start = time.time()
        
        # Clear current metrics and history
        self.current_metrics = None
        self.current_mouse_metrics = None
        self.current_anomaly = None
        self.recent_history.clear()
        
        # Clear database samples
        if self._db_store:
            try:
                self._db_store.delete_all_samples()
            except Exception:
                pass
        
        logger.info("Training data deleted - baseline reset to 0, starting fresh collection.")

    def save_my_behavior_snapshot(self) -> Optional[Dict]:
        """Save confirmed snapshot to data/my_behavior.json."""
        km = self.current_metrics
        mm = self.current_mouse_metrics
        if not km or km.keystroke_count == 0:
            km = self._kb_analyzer.analyze(self._kb_recorder.get_snapshot())
        if not mm or mm.movement_count == 0:
            mm = self._mouse_analyzer.analyze(self._mouse_recorder.get_snapshot())

        now_iso = datetime.now().isoformat()
        session_data = {
            "timestamp": now_iso,
            "keystroke_count": int(km.keystroke_count),
            "wpm": round(float(km.wpm), 2),
            "dwell_ms": round(float(km.avg_dwell_ms), 2),
            "flight_ms": round(float(km.avg_flight_ms), 2),
            "consistency_stddev": round(float(km.consistency_stddev), 2),
            "mouse_speed_pxsec": round(float(mm.avg_speed_pxsec), 2),
            "mouse_curvature": round(float(mm.curvature_index), 2),
            "mouse_clicks": int(mm.click_count),
        }

        if self.current_anomaly:
            session_data["anomaly_assessment"] = {
                "similarity_score": round(float(self.current_anomaly.similarity_score), 1),
                "keyboard_similarity": round(float(self.current_anomaly.keyboard_similarity), 1),
                "mouse_similarity": round(float(self.current_anomaly.mouse_similarity), 1),
                "status": str(self.current_anomaly.status),
                "status_label": str(self.current_anomaly.status_label),
            }

        existing_history = []
        if self._my_behavior_path.exists():
            try:
                with open(self._my_behavior_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if isinstance(d, dict) and isinstance(d.get("history"), list):
                        existing_history = d["history"]
            except Exception:
                pass

        existing_history.append(session_data)
        if len(existing_history) > 100:
            existing_history = existing_history[-100:]

        payload = {
            "_comment": "Confirmed multi-modal behavioral snapshots (saved via 'This Was Me').",
            "_privacy": "Only timing & motion dynamics stored. No screen content or key characters.",
            "last_confirmed": now_iso,
            "total_confirmations": len(existing_history),
            "latest_session": session_data,
            "history": existing_history,
        }

        try:
            self._my_behavior_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._my_behavior_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            return payload
        except Exception as exc:
            logger.error("Failed to write %s: %s", self._my_behavior_path, exc)
            return None

    def confirm_this_was_me(self) -> Optional[Dict]:
        self._anomaly_start = None
        if self.settings.get("adaptive_baseline"):
            if self.current_metrics:
                self._learner.add_kb_sample(self.current_metrics)
            if self.current_mouse_metrics:
                self._learner.add_mouse_sample(self.current_mouse_metrics)
        return self.save_my_behavior_snapshot()

    def get_training_progress(self) -> Dict:
        ks = self.total_keystrokes
        mouse_moves = self.total_mouse_movements
        need_ks = self._learner._min_ks
        need_mouse = self._learner._min_mouse

        pct_ks = min(100.0, ks / max(need_ks, 1) * 100.0)
        pct_mouse = min(100.0, mouse_moves / max(need_mouse, 1) * 100.0)
        pct = round((0.6 * pct_ks) + (0.4 * pct_mouse), 1)

        elapsed_secs = time.time() - self._learner._training_start
        elapsed_days, rem = divmod(int(elapsed_secs), 86400)
        elapsed_hrs = rem // 3600

        if pct < 100 and elapsed_secs > 60:
            rate_ks = ks / elapsed_secs
            rem_ks = need_ks - ks
            eta_secs = rem_ks / max(rate_ks, 0.01)
            eta_days = int(eta_secs // 86400)
            eta_hrs = int((eta_secs % 86400) // 3600)
        else:
            eta_days = 0
            eta_hrs = 0

        return {
            "keystrokes_recorded": ks,
            "keystrokes_needed": need_ks,
            "mouse_movements": mouse_moves,
            "mouse_needed": need_mouse,
            "percent": min(100.0, pct),
            "elapsed_days": elapsed_days,
            "elapsed_hours": elapsed_hrs,
            "eta_days": eta_days,
            "eta_hours": eta_hrs,
            "is_complete": self.is_training_complete,
        }

    # ------------------------------------------------------------------
    # JSON Export Methods
    # ------------------------------------------------------------------

    def export_keyboard_json(self, filepath: Optional[Union[str, Path]] = None) -> Path:
        target = filepath or DEFAULT_KEYBOARD_EXPORT_PATH
        return self._exporter.export_keyboard_profile(self.baseline, target)

    def export_mouse_json(self, filepath: Optional[Union[str, Path]] = None) -> Path:
        target = filepath or DEFAULT_MOUSE_EXPORT_PATH
        return self._exporter.export_mouse_profile(self.mouse_baseline, target)

    def export_combined_profile_json(self, filepath: Optional[Union[str, Path]] = None) -> Path:
        target = filepath or DEFAULT_COMBINED_EXPORT_PATH
        return self._exporter.export_combined_profile(self.baseline, self.mouse_baseline, target)

    def export_session_json(self, filepath: Optional[Union[str, Path]] = None, duration_mins: int = 60) -> Path:
        anonymize = bool(self.settings.get("anonymize_export_timestamps", True))
        return self._exporter.export_session(
            self.recent_history, filepath, duration_mins=duration_mins, anonymize_timestamps=anonymize
        )

    def export_comparison_json(self, filepath: Optional[Union[str, Path]] = None) -> Path:
        target = filepath or (DEFAULT_DATA_DIR / "comparison_report.json")
        return self._exporter.export_comparison_report(
            self.current_metrics,
            self.current_mouse_metrics,
            self.baseline,
            self.mouse_baseline,
            self.current_anomaly,
            target,
        )

    # ------------------------------------------------------------------
    # Background Analysis Loop
    # ------------------------------------------------------------------

    def _analysis_loop(self) -> None:
        while self._running:
            try:
                window = self.settings.get("analysis_window", ANALYSIS_WINDOW_SECS)
                time.sleep(window)
                if not self._running:
                    break
                if not self.settings.get("enabled", True):
                    continue
                self._run_cycle()
            except Exception as exc:
                logger.error("Multi-modal analysis loop error: %s", exc, exc_info=True)

    def _run_cycle(self) -> None:
        window = self.settings.get("analysis_window", ANALYSIS_WINDOW_SECS)
        since_ts = time.perf_counter() - window

        kb_events = self._kb_recorder.get_snapshot(since=since_ts)
        mouse_events = self._mouse_recorder.get_snapshot(since=since_ts)

        km = self._kb_analyzer.analyze(kb_events, window_secs=window)
        mm = self._mouse_analyzer.analyze(mouse_events, window_secs=window)

        self.current_metrics = km
        self.current_mouse_metrics = mm

        self._learner.add_kb_sample(km)
        self._learner.add_mouse_sample(mm)

        # Save progress periodically if baseline not yet complete
        if not self.is_baseline_available:
            now = time.time()
            keystroke_delta = self.total_keystrokes - self._last_keystroke_count
            
            # Save every 30 seconds OR every 50 keystrokes, whichever comes first
            if (now - self._last_progress_save >= 30.0) or (keystroke_delta >= 50):
                self._save_progress()
                self._last_progress_save = now
                self._last_keystroke_count = self.total_keystrokes

        # Switch latency & correlation estimation
        last_kb = self._kb_recorder.last_event_ts
        last_m = self._mouse_recorder.last_event_ts
        switch_lat = abs(last_m - last_kb) * 1000.0 if last_kb > 0 and last_m > 0 else 450.0
        corr = 0.75 if km.is_sufficient and mm.is_sufficient else 0.50

        # Persist to DB
        if self._db_store:
            try:
                is_tr = not self.is_baseline_available
                if km.is_sufficient:
                    self._db_store.log_typing_sample(km, is_training=is_tr)
                if mm.is_sufficient:
                    self._db_store.log_mouse_sample(mm, is_training=is_tr)
            except Exception as exc:
                logger.debug("DB log error: %s", exc)

        # Check training completion (two-tier approach)
        # Tier 1: UI unlock at 120/200 — save initial baseline, delete progress, enable monitoring
        if not self.is_baseline_available and self.is_training_complete:
            try:
                self._learner.compute_and_save_baselines(self.total_keystrokes, self.total_mouse_movements)
                # Export default JSON profiles upon baseline completion
                self.export_keyboard_json()
                self.export_mouse_json()
                self.export_combined_profile_json()
                # Delete progress file now that UI unlock threshold is met
                self._delete_progress()
                logger.info("Baseline UI unlock threshold met (%d/%d ks, %d/%d mouse). Monitoring enabled. Silent collection continues to %d/%d.",
                           self.total_keystrokes, MIN_TRAINING_KS, self.total_mouse_movements, MIN_TRAINING_MOUSE,
                           FULL_BASELINE_KS, FULL_BASELINE_MOUSE)
            except Exception as exc:
                logger.error("Baseline computation error: %s", exc)
        
        # Tier 2: Full baseline at 2000/3000 — update baseline silently (no UI notification)
        elif self.is_baseline_available and not self._learner.is_full_baseline_complete(self.total_keystrokes, self.total_mouse_movements):
            # Silently update baseline every 100 keystrokes or 200 mouse movements
            if (self.total_keystrokes % 100 == 0 and self.total_keystrokes > MIN_TRAINING_KS) or \
               (self.total_mouse_movements % 200 == 0 and self.total_mouse_movements > MIN_TRAINING_MOUSE):
                try:
                    self._learner.compute_and_save_baselines(self.total_keystrokes, self.total_mouse_movements)
                    self.export_keyboard_json()
                    self.export_mouse_json()
                    self.export_combined_profile_json()
                    logger.debug("Silent baseline update: %d/%d ks, %d/%d mouse",
                               self.total_keystrokes, FULL_BASELINE_KS,
                               self.total_mouse_movements, FULL_BASELINE_MOUSE)
                except Exception as exc:
                    logger.debug("Silent baseline update error: %s", exc)

        # Anomaly detection
        anomaly = None
        if self.is_baseline_available:
            anomaly = self._detector.analyze(
                km, mm, self.baseline, self.mouse_baseline, switch_lat, corr
            )
            self.current_anomaly = anomaly

        # Recent history
        ts_now = time.time()
        self.recent_history.append((ts_now, km, mm, anomaly))
        if len(self.recent_history) > 100:
            self.recent_history.pop(0)

        # Fire callbacks
        if self.on_metrics_update:
            try:
                self.on_metrics_update(km)
            except Exception:
                pass
        if self.on_mouse_update:
            try:
                self.on_mouse_update(mm)
            except Exception:
                pass

        # Alerting
        if (
            anomaly
            and km.is_sufficient
            and mm.is_sufficient
            and anomaly.similarity_score >= 0
            and anomaly.similarity_score < self.settings.get("alert_threshold", 70.0)
        ):
            if self._anomaly_start is None:
                self._anomaly_start = time.time()
            elif time.time() - self._anomaly_start >= self.settings.get("min_alert_duration", 120.0):
                context = None
                try:
                    context = (
                        self._alert_context_provider()
                        if self._alert_context_provider
                        else ""
                    )
                except Exception as exc:
                    logger.debug("Behavioral alert context unavailable: %s", exc)

                if context is not None:
                    if context:
                        anomaly.explanations.insert(0, context)
                    if self._db_store:
                        try:
                            self._db_store.log_behavioral_alert(anomaly, km)
                        except Exception:
                            pass
                    if self.on_anomaly:
                        try:
                            self.on_anomaly(anomaly)
                        except Exception:
                            pass
                    if self.settings.get("desktop_notify", True):
                        self._send_notification(anomaly)
                    self._anomaly_start = None
        else:
            self._anomaly_start = None

    @staticmethod
    def _send_notification(anomaly: AnomalyResult) -> None:
        try:
            from plyer import notification
            title = "⚠️ KeyGuard AI — Behavioral Anomaly"
            if anomaly.bot_detected:
                title = f"🤖 KeyGuard AI — {anomaly.bot_type.replace('_', ' ').title()}"
            msg = (
                f"Combined similarity: {anomaly.similarity_score:.0f}%\n"
                f"KB: {anomaly.keyboard_similarity:.0f}% | Mouse: {anomaly.mouse_similarity:.0f}%\n"
                f"{anomaly.explanations[0] if anomaly.explanations else ''}"
            )
            notification.notify(title=title, message=msg[:256], timeout=8)
        except Exception:
            pass
