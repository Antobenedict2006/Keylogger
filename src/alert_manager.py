"""
alert_manager.py
================
Stage 4 (part 1) of the pipeline: Alert & Response Module.

Responsibilities:
  - Receive ClassificationResult objects from the classifier.
  - Deduplicate / suppress repeat alerts for the same PID within a cooldown
    window to avoid notification storms.
  - Fire desktop notifications via plyer (falls back to Windows MessageBox).
  - Offer three one-click response actions:
      * terminate   — kill the process immediately via psutil
      * quarantine  — suspend the process and move its executable to a
                      quarantine folder (isolates it without permanent deletion)
      * whitelist   — record the PID/exe in a persistent whitelist so the
                      process is never flagged again; feeds back into the
                      classifier skip-list
  - Emit ActionResult objects that are picked up by the db_logger and UI.
  - Maintain an in-memory list of recent alerts consumed by the dashboard.

Thread safety
-------------
  All public methods are safe to call from any thread.  Internal state is
  protected by a single RLock.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

import psutil

from .classifier import ClassificationResult, RiskLevel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

from .paths import DEFAULT_QUARANTINE_DIR, DEFAULT_WHITELIST_PATH

# Seconds before the same PID can trigger another desktop notification
ALERT_COOLDOWN: float = 60.0

# Maximum alerts kept in the in-memory recent-alerts buffer for the UI
MAX_RECENT_ALERTS: int = 200


# ---------------------------------------------------------------------------
# Response action types
# ---------------------------------------------------------------------------

class ResponseAction(Enum):
    TERMINATE  = "terminate"
    QUARANTINE = "quarantine"
    WHITELIST  = "whitelist"
    DISMISS    = "dismiss"


@dataclass
class ActionResult:
    """Outcome of a user-triggered response action."""
    pid:       int
    name:      str
    action:    ResponseAction
    success:   bool
    message:   str
    timestamp: float = field(default_factory=time.time)

    def summary(self) -> str:
        status = "✓" if self.success else "✗"
        return f"[{status}] {self.action.value.upper()} PID {self.pid} ({self.name}): {self.message}"


# ---------------------------------------------------------------------------
# Alert record (stored in recent-alerts buffer)
# ---------------------------------------------------------------------------

@dataclass
class AlertRecord:
    result:       ClassificationResult
    notified:     bool = False          # True once desktop notification was fired
    action_taken: Optional[ResponseAction] = None
    action_result: Optional[ActionResult]  = None
    timestamp:    float = field(default_factory=time.time)

    @property
    def pid(self) -> int:
        return self.result.pid

    @property
    def risk_level(self) -> RiskLevel:
        return self.result.risk_level


# ---------------------------------------------------------------------------
# Whitelist manager
# ---------------------------------------------------------------------------

class _WhitelistManager:
    """
    Persists a set of whitelisted exe paths and process names to
    whitelist.json.  Whitelisted items are never scored / alerted.
    """

    def __init__(self, path: Path = DEFAULT_WHITELIST_PATH) -> None:
        self._path = path
        self._exe_set:  Set[str] = set()
        self._name_set: Set[str] = set()
        self._lock = threading.Lock()
        self._load()

    def is_whitelisted(self, result: ClassificationResult) -> bool:
        with self._lock:
            if result.exe and result.exe.lower() in self._exe_set:
                return True
            if result.name.lower() in self._name_set:
                return True
        return False

    def add(self, result: ClassificationResult) -> None:
        with self._lock:
            if result.exe:
                self._exe_set.add(result.exe.lower())
            self._name_set.add(result.name.lower())
            self._save()
        logger.info(
            "Whitelisted: name=%s exe=%s", result.name, result.exe
        )

    def _load(self) -> None:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._exe_set  = set(data.get("exe_paths", []))
                self._name_set = set(data.get("process_names", []))
                logger.debug(
                    "Loaded whitelist: %d exes, %d names.",
                    len(self._exe_set), len(self._name_set),
                )
        except Exception as exc:
            logger.warning("Could not load whitelist: %s", exc)

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "exe_paths":      sorted(self._exe_set),
                "process_names":  sorted(self._name_set),
                "updated_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self._path.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.error("Could not save whitelist: %s", exc)


# ---------------------------------------------------------------------------
# Response executor
# ---------------------------------------------------------------------------

class _ResponseExecutor:
    """Executes terminate / quarantine / whitelist actions."""

    def __init__(
        self,
        quarantine_dir: Path,
        whitelist: _WhitelistManager,
    ) -> None:
        self._quarantine_dir = quarantine_dir
        self._whitelist = whitelist

    def execute(
        self,
        action: ResponseAction,
        result: ClassificationResult,
    ) -> ActionResult:
        handlers = {
            ResponseAction.TERMINATE:  self._terminate,
            ResponseAction.QUARANTINE: self._quarantine,
            ResponseAction.WHITELIST:  self._whitelist_action,
            ResponseAction.DISMISS:    self._dismiss,
        }
        handler = handlers.get(action, self._dismiss)
        return handler(result)

    # ------------------------------------------------------------------

    def _terminate(self, result: ClassificationResult) -> ActionResult:
        try:
            proc = psutil.Process(result.pid)
            proc.terminate()
            # Give it 3 seconds to exit cleanly, then force-kill
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            msg = f"Process {result.name} (PID {result.pid}) terminated."
            logger.warning(msg)
            return ActionResult(
                pid=result.pid, name=result.name,
                action=ResponseAction.TERMINATE,
                success=True, message=msg,
            )
        except psutil.NoSuchProcess:
            msg = f"PID {result.pid} no longer exists."
            return ActionResult(
                pid=result.pid, name=result.name,
                action=ResponseAction.TERMINATE,
                success=False, message=msg,
            )
        except psutil.AccessDenied as exc:
            msg = f"Access denied terminating PID {result.pid}: {exc}"
            logger.error(msg)
            return ActionResult(
                pid=result.pid, name=result.name,
                action=ResponseAction.TERMINATE,
                success=False, message=msg,
            )
        except Exception as exc:
            msg = f"Unexpected error terminating PID {result.pid}: {exc}"
            logger.error(msg)
            return ActionResult(
                pid=result.pid, name=result.name,
                action=ResponseAction.TERMINATE,
                success=False, message=msg,
            )

    def _quarantine(self, result: ClassificationResult) -> ActionResult:
        """
        Quarantine steps:
          1. Suspend the process (SIGSTOP / NtSuspendProcess).
          2. Copy the executable to the quarantine folder.
          3. Record quarantine metadata (JSON sidecar).
        We do NOT delete the original — the user decides later.
        """
        try:
            proc = psutil.Process(result.pid)

            # Step 1: Suspend
            proc.suspend()

            # Step 2: Copy exe to quarantine
            dest_path: Optional[Path] = None
            if result.exe and Path(result.exe).exists():
                self._quarantine_dir.mkdir(parents=True, exist_ok=True)
                safe_name = (
                    f"{result.name}_{result.pid}_"
                    f"{int(time.time())}.quarantined"
                )
                dest_path = self._quarantine_dir / safe_name
                shutil.copy2(result.exe, dest_path)

                # Step 3: Write metadata sidecar
                meta = {
                    "original_path": result.exe,
                    "pid":           result.pid,
                    "name":          result.name,
                    "score":         result.score,
                    "risk_level":    result.risk_level.value,
                    "reasons":       result.reasons,
                    "quarantined_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    ),
                }
                meta_path = dest_path.with_suffix(".json")
                meta_path.write_text(
                    json.dumps(meta, indent=2), encoding="utf-8"
                )

            msg = (
                f"Process {result.name} (PID {result.pid}) suspended. "
                + (f"Exe copied to {dest_path}." if dest_path else "Exe not found.")
            )
            logger.warning(msg)
            return ActionResult(
                pid=result.pid, name=result.name,
                action=ResponseAction.QUARANTINE,
                success=True, message=msg,
            )

        except psutil.NoSuchProcess:
            msg = f"PID {result.pid} no longer exists."
            return ActionResult(
                pid=result.pid, name=result.name,
                action=ResponseAction.QUARANTINE,
                success=False, message=msg,
            )
        except psutil.AccessDenied as exc:
            msg = f"Access denied quarantining PID {result.pid}: {exc}"
            logger.error(msg)
            return ActionResult(
                pid=result.pid, name=result.name,
                action=ResponseAction.QUARANTINE,
                success=False, message=msg,
            )
        except Exception as exc:
            msg = f"Quarantine failed for PID {result.pid}: {exc}"
            logger.error(msg)
            return ActionResult(
                pid=result.pid, name=result.name,
                action=ResponseAction.QUARANTINE,
                success=False, message=msg,
            )

    def _whitelist_action(self, result: ClassificationResult) -> ActionResult:
        try:
            self._whitelist.add(result)
            msg = (
                f"{result.name} added to whitelist. "
                "It will no longer trigger alerts."
            )
            return ActionResult(
                pid=result.pid, name=result.name,
                action=ResponseAction.WHITELIST,
                success=True, message=msg,
            )
        except Exception as exc:
            msg = f"Whitelist failed: {exc}"
            return ActionResult(
                pid=result.pid, name=result.name,
                action=ResponseAction.WHITELIST,
                success=False, message=msg,
            )

    @staticmethod
    def _dismiss(result: ClassificationResult) -> ActionResult:
        return ActionResult(
            pid=result.pid, name=result.name,
            action=ResponseAction.DISMISS,
            success=True, message="Alert dismissed.",
        )


# ---------------------------------------------------------------------------
# Desktop notification helper
# ---------------------------------------------------------------------------

def _send_desktop_notification(result: ClassificationResult) -> None:
    """
    Fire a desktop notification via plyer.  Falls back to a Windows
    MessageBox (non-blocking) if plyer is unavailable.
    """
    title = f"{result.risk_level.emoji} {result.risk_level.display_name} — {result.name}"
    reasons_txt = (
        "\n".join(f"• {r}" for r in result.reasons[:4])
        if result.reasons
        else "Suspicious behaviour detected."
    )
    body = f"PID {result.pid}\nScore: {result.score:.0%}\n\n{reasons_txt}"

    # Windows NOTIFYICONDATAW limits: title ≤ 63 chars, message ≤ 255 chars.
    # Truncate gracefully so plyer never raises ValueError.
    MAX_TITLE = 63
    MAX_BODY  = 255
    if len(title) > MAX_TITLE:
        title = title[:MAX_TITLE - 1] + "…"
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY - 1] + "…"

    try:
        from plyer import notification as plyer_notif
        plyer_notif.notify(
            title=title,
            message=body,
            app_name="Keylogger Detector",
            timeout=10,
        )
        return
    except Exception:
        pass

    # Fallback: Windows MessageBox (non-blocking thread)
    try:
        import ctypes
        MB_ICONWARNING = 0x30
        MB_OK          = 0x00
        def _show():
            ctypes.windll.user32.MessageBoxW(
                0, body, title, MB_ICONWARNING | MB_OK
            )
        threading.Thread(target=_show, daemon=True).start()
    except Exception as exc:
        logger.warning("Could not show desktop notification: %s", exc)


# ---------------------------------------------------------------------------
# AlertManager — main public class
# ---------------------------------------------------------------------------

class AlertManager:
    """
    Central hub for alert deduplication, notification, and response actions.

    Usage::

        def on_action(action_result: ActionResult):
            db_logger.log_action(action_result)

        am = AlertManager(action_callback=on_action)
        am.process_results(classification_results)

        # Later, from UI:
        am.take_action(ResponseAction.TERMINATE, alert_record)
    """

    def __init__(
        self,
        action_callback: Optional[Callable[[ActionResult], None]] = None,
        quarantine_dir: Path = DEFAULT_QUARANTINE_DIR,
        whitelist_path: Path = DEFAULT_WHITELIST_PATH,
        alert_cooldown: float = ALERT_COOLDOWN,
        min_notify_risk: RiskLevel = RiskLevel.SUSPICIOUS,
    ) -> None:
        self._action_callback = action_callback
        self._alert_cooldown = alert_cooldown
        self._min_notify_risk = min_notify_risk

        self._whitelist  = _WhitelistManager(whitelist_path)
        self._executor   = _ResponseExecutor(quarantine_dir, self._whitelist)

        self._lock = threading.RLock()
        # pid -> last notification timestamp
        self._last_notified: Dict[int, float] = {}
        # Ordered list of AlertRecord for UI consumption
        self._recent_alerts: List[AlertRecord] = []

    # ------------------------------------------------------------------
    # Pipeline input
    # ------------------------------------------------------------------

    def process_results(
        self, results: List[ClassificationResult]
    ) -> List[AlertRecord]:
        """
        Ingest a batch of ClassificationResults.
        Whitelisted and SAFE results are silently dropped.
        SUSPICIOUS / MALICIOUS results are recorded and notified (with cooldown).
        Returns newly created AlertRecord objects for the current batch.
        """
        new_records: List[AlertRecord] = []

        for result in results:
            # Skip safe & whitelisted
            if result.risk_level == RiskLevel.SAFE:
                continue
            if self._whitelist.is_whitelisted(result):
                logger.debug(
                    "PID %d (%s) is whitelisted — skipping.",
                    result.pid, result.name,
                )
                continue

            record = AlertRecord(result=result)

            # Check cooldown
            now = time.time()
            with self._lock:
                last = self._last_notified.get(result.pid, 0.0)
                should_notify = (
                    now - last >= self._alert_cooldown
                    and self._risk_meets_threshold(result.risk_level)
                )
                if should_notify:
                    self._last_notified[result.pid] = now

            if should_notify:
                record.notified = True
                threading.Thread(
                    target=_send_desktop_notification,
                    args=(result,),
                    daemon=True,
                ).start()
                logger.warning(result.summary())

            # Store in recent buffer
            with self._lock:
                self._recent_alerts.append(record)
                if len(self._recent_alerts) > MAX_RECENT_ALERTS:
                    self._recent_alerts = self._recent_alerts[-MAX_RECENT_ALERTS:]

            new_records.append(record)

        return new_records

    # ------------------------------------------------------------------
    # Response actions (called from UI)
    # ------------------------------------------------------------------

    def take_action(
        self,
        action: ResponseAction,
        record: AlertRecord,
    ) -> ActionResult:
        """
        Execute a response action on a previously recorded alert.
        Fires the action_callback and updates the record in place.
        """
        action_result = self._executor.execute(action, record.result)

        with self._lock:
            record.action_taken  = action
            record.action_result = action_result

        if self._action_callback:
            try:
                self._action_callback(action_result)
            except Exception as exc:
                logger.error("action_callback raised: %s", exc)

        return action_result

    def take_action_by_pid(
        self,
        action: ResponseAction,
        pid: int,
    ) -> Optional[ActionResult]:
        """
        Convenience: look up the most recent alert for *pid* and act on it.
        Returns None if no matching alert is found.
        """
        with self._lock:
            # Most recent first
            for record in reversed(self._recent_alerts):
                if record.pid == pid:
                    return self.take_action(action, record)
        return None

    # ------------------------------------------------------------------
    # UI data access
    # ------------------------------------------------------------------

    @property
    def recent_alerts(self) -> List[AlertRecord]:
        """Snapshot of the recent-alerts buffer (thread-safe copy)."""
        with self._lock:
            return list(self._recent_alerts)

    def pending_alerts(self) -> List[AlertRecord]:
        """Alerts that have not had an action taken yet."""
        with self._lock:
            return [
                r for r in self._recent_alerts
                if r.action_taken is None
            ]

    def clear_alerts(self) -> None:
        with self._lock:
            self._recent_alerts.clear()

    # ------------------------------------------------------------------
    # Whitelist passthrough
    # ------------------------------------------------------------------

    def is_whitelisted(self, result: ClassificationResult) -> bool:
        return self._whitelist.is_whitelisted(result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _risk_meets_threshold(self, risk: RiskLevel) -> bool:
        order = {RiskLevel.SAFE: 0, RiskLevel.SUSPICIOUS: 1, RiskLevel.MALICIOUS: 2}
        return order[risk] >= order[self._min_notify_risk]
