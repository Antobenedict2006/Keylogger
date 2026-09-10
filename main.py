"""
main.py
=======
Entry point for the AI-Based Keylogger Detection System.

Pipeline wiring
---------------
  ProcessMonitor  →  FeatureExtractor  →  KeyloggerClassifier
                                       →  AlertManager  →  DBLogger
                                                        →  Dashboard (UI)

Startup sequence
----------------
  1. Parse CLI args / load config.
  2. Initialise DBLogger (creates DB file if absent).
  3. Initialise KeyloggerClassifier (loads model if available).
  4. Initialise AlertManager (loads whitelist).
  5. Initialise FeatureExtractor.
  6. Start ProcessMonitor background thread.
  7. Start model hot-reload watcher.
  8. Launch Dashboard (Tkinter mainloop — blocks on main thread).
  9. On quit: stop monitor, flush DB, exit cleanly.

Run
---
  python main.py                  # full GUI mode
  python main.py --no-gui         # headless / service mode
  python main.py --help           # show all options
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path when run directly
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.monitor          import ProcessMonitor, ProcessSnapshot
from src.feature_extractor import FeatureExtractor, FeatureVector
from src.classifier        import KeyloggerClassifier, RiskLevel
from src.alert_manager     import AlertManager, ActionResult, ResponseAction
from src.db_logger         import DBLogger

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE   = "%H:%M:%S"

def _setup_logging(level: str, log_file: Optional[Path] = None) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=numeric, format=LOG_FORMAT,
                        datefmt=LOG_DATE, handlers=handlers)
    # Quieten noisy third-party loggers
    for noisy in ("PIL", "pystray", "comtypes"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="keylogger-detector",
        description="AI-Based Keylogger Detection System",
    )
    p.add_argument(
        "--no-gui", action="store_true",
        help="Run in headless mode (no Tkinter window or tray icon).",
    )
    p.add_argument(
        "--scan-interval", type=float, default=5.0, metavar="SECONDS",
        help="Seconds between process scans (default: 5).",
    )
    p.add_argument(
        "--model", type=Path,
        default=PROJECT_ROOT / "models" / "keylogger_detector.joblib",
        metavar="PATH",
        help="Path to trained model file (.joblib).",
    )
    p.add_argument(
        "--db", type=Path,
        default=PROJECT_ROOT / "logs" / "keylogger_events.db",
        metavar="PATH",
        help="Path to SQLite event database.",
    )
    p.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console log verbosity (default: INFO).",
    )
    p.add_argument(
        "--log-file", type=Path,
        default=PROJECT_ROOT / "logs" / "detector.log",
        metavar="PATH",
        help="Optional file to write logs to.",
    )
    p.add_argument(
        "--alert-threshold", choices=["suspicious", "malicious"],
        default="suspicious",
        help="Minimum risk level that triggers a desktop notification.",
    )
    p.add_argument(
        "--log-snapshots", action="store_true",
        help="Write every raw ProcessSnapshot to the DB (increases disk use).",
    )
    return p


# ---------------------------------------------------------------------------
# Detection pipeline callback
# ---------------------------------------------------------------------------

class DetectionPipeline:
    """
    Wires Monitor → FeatureExtractor → Classifier → AlertManager → DBLogger.

    The pipeline callback is invoked by the ProcessMonitor background thread
    every SCAN_INTERVAL seconds with a list[ProcessSnapshot].
    """

    def __init__(
        self,
        extractor:  FeatureExtractor,
        classifier: KeyloggerClassifier,
        alert_mgr:  AlertManager,
        db_logger:  DBLogger,
    ) -> None:
        self._extractor  = extractor
        self._classifier = classifier
        self._alert_mgr  = alert_mgr
        self._db         = db_logger

        # Metrics
        self._scan_count  = 0
        self._total_procs = 0
        self._threat_count = 0
        self._last_scan_time: float = 0.0

        # Keep a {pid: detection_id} map so actions can link to their detection
        self._pid_to_detection_id: Dict[int, int] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Called by ProcessMonitor on each scan
    # ------------------------------------------------------------------

    def on_snapshots(self, snapshots: List[ProcessSnapshot]) -> None:
        scan_start = time.time()
        self._scan_count  += 1
        self._total_procs += len(snapshots)

        # Stage 2: Feature extraction
        feature_vectors: List[FeatureVector] = self._extractor.update(snapshots)

        # Stage 3: Classification
        results = self._classifier.batch_classify(feature_vectors)

        # Split threats from clean
        threats = [r for r in results if r.is_threat]
        self._threat_count += len(threats)

        # Stage 4a: Alert & Response
        new_records = self._alert_mgr.process_results(threats)

        # Stage 4b: Log threats to DB
        fv_map = {fv.pid: fv for fv in feature_vectors}
        for result in threats:
            fv = fv_map.get(result.pid)
            det_id = self._db.log_detection(result, fv)
            with self._lock:
                self._pid_to_detection_id[result.pid] = det_id

        # Stage 4c: Log raw snapshots (if enabled)
        self._db.log_snapshots_batch(snapshots)

        self._last_scan_time = time.time() - scan_start

        if self._scan_count % 12 == 0:   # log a heartbeat every ~1 min
            logger.info(
                "Heartbeat | scans=%d  procs_scanned=%d  threats_found=%d  "
                "last_scan=%.2fs  model=%s",
                self._scan_count,
                self._total_procs,
                self._threat_count,
                self._last_scan_time,
                "ML" if self._classifier.using_ml_model else "heuristic",
            )

    # ------------------------------------------------------------------
    # Action logging callback (passed to AlertManager)
    # ------------------------------------------------------------------

    def on_action(self, action_result: ActionResult) -> None:
        """Log a user-triggered action, linking it to its detection row."""
        with self._lock:
            det_id = self._pid_to_detection_id.get(action_result.pid)
        self._db.log_action(action_result, detection_id=det_id)

    # ------------------------------------------------------------------
    # Status string for the UI stats tab
    # ------------------------------------------------------------------

    def model_status(self) -> str:
        if self._classifier.using_ml_model:
            return (
                f"ML model active (v{self._classifier.model_version})  |  "
                f"scans={self._scan_count}  threats={self._threat_count}"
            )
        return (
            f"Heuristic mode (no trained model loaded)  |  "
            f"scans={self._scan_count}  threats={self._threat_count}"
        )


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_shutdown_event = threading.Event()

def _install_signal_handlers() -> None:
    """Install SIGINT / SIGTERM handlers for clean shutdown."""
    def _handler(sig, _frame):
        logger.info("Signal %s received — shutting down…", sig)
        _shutdown_event.set()

    signal.signal(signal.SIGINT,  _handler)
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (OSError, ValueError):
        pass   # SIGTERM not available on all platforms


# ---------------------------------------------------------------------------
# Headless mode loop
# ---------------------------------------------------------------------------

def _run_headless(monitor: ProcessMonitor) -> None:
    """Block until SIGINT / SIGTERM, then stop the monitor."""
    logger.info("Running in headless mode. Press Ctrl+C to stop.")
    try:
        while not _shutdown_event.is_set():
            _shutdown_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        pass
    logger.info("Stopping monitor…")
    monitor.stop()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = _build_parser()
    args   = parser.parse_args()

    _setup_logging(args.log_level, args.log_file)
    _install_signal_handlers()

    logger.info("=" * 60)
    logger.info("  AI-Based Keylogger Detection System  starting up")
    logger.info("  Model path : %s", args.model)
    logger.info("  Database   : %s", args.db)
    logger.info("  GUI mode   : %s", "off" if args.no_gui else "on")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 1. Database
    # ------------------------------------------------------------------
    db_logger = DBLogger(
        db_path=args.db,
        log_all_snapshots=args.log_snapshots,
    )

    # ------------------------------------------------------------------
    # 2. Classifier
    # ------------------------------------------------------------------
    classifier = KeyloggerClassifier(model_path=args.model)
    loaded = classifier.load_model()
    if not loaded:
        logger.warning(
            "No trained model found at %s — using heuristic scoring. "
            "Run tools/train_model.py to generate one.",
            args.model,
        )
    classifier.start_hot_reload()

    # ------------------------------------------------------------------
    # 3. Alert manager
    # ------------------------------------------------------------------
    min_risk = (
        RiskLevel.MALICIOUS if args.alert_threshold == "malicious"
        else RiskLevel.SUSPICIOUS
    )

    # We wire the action callback after building the pipeline
    alert_mgr = AlertManager(
        action_callback=None,     # patched below
        min_notify_risk=min_risk,
    )

    # ------------------------------------------------------------------
    # 4. Feature extractor & pipeline
    # ------------------------------------------------------------------
    extractor = FeatureExtractor()
    pipeline  = DetectionPipeline(
        extractor=extractor,
        classifier=classifier,
        alert_mgr=alert_mgr,
        db_logger=db_logger,
    )

    # Patch action callback now that pipeline exists
    alert_mgr._action_callback = pipeline.on_action

    # ------------------------------------------------------------------
    # 5. Process monitor
    # ------------------------------------------------------------------
    monitor = ProcessMonitor(
        callback=pipeline.on_snapshots,
        scan_interval=args.scan_interval,
    )
    monitor.start()
    logger.info("Monitor started (scan interval: %.1fs).", args.scan_interval)

    # ------------------------------------------------------------------
    # 6. UI  (or headless)
    # ------------------------------------------------------------------
    exit_code = 0
    try:
        if args.no_gui:
            _run_headless(monitor)
        else:
            # Dashboard.run() blocks on the Tkinter mainloop
            from src.ui.dashboard import Dashboard

            def _on_pause(paused: bool) -> None:
                if paused:
                    monitor.stop()
                    logger.info("Monitoring paused by user.")
                else:
                    monitor.start()
                    logger.info("Monitoring resumed by user.")

            def _on_quit() -> None:
                logger.info("Quit requested from UI.")
                _shutdown_event.set()

            dashboard = Dashboard(
                alert_manager=alert_mgr,
                db_logger=db_logger,
                get_model_status=pipeline.model_status,
                on_pause=_on_pause,
                on_quit=_on_quit,
            )
            dashboard.run()   # blocks until window closed / quit

    except Exception as exc:
        logger.exception("Fatal error in main loop: %s", exc)
        exit_code = 1

    # ------------------------------------------------------------------
    # 7. Shutdown
    # ------------------------------------------------------------------
    logger.info("Shutting down…")
    try:
        monitor.stop()
    except Exception:
        pass
    try:
        classifier.stop_hot_reload()
    except Exception:
        pass
    try:
        db_logger.close()
    except Exception:
        pass

    logger.info("Goodbye.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
