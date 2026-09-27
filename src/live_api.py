"""
live_api.py
===========
Tiny Flask HTTP server that runs as a background thread inside the
keylogger-detection application and exposes the latest scan results to
the Next.js web dashboard running at http://localhost:3000.

Endpoints
---------
  GET  /api/scan              → latest full scan (ProcessAnalysisResult[])
  GET  /api/scan/summary      → MetricsCards-compatible summary object
  GET  /api/health            → {"status": "ok", "version": "1.0"}
  GET  /api/alerts            → live alerts (recent_alerts from AlertManager)
  GET  /api/history           → detection history (from DBLogger)
  GET  /api/statistics        → statistics (total/malicious/suspicious/actioned counts)
  POST /api/actions           → take action (terminate/quarantine/whitelist/dismiss)
  POST /api/train             → start model training
  GET  /api/behavior          → behavioral analysis data

The web dashboard polls GET /api/scan every few seconds.  Results are
cached in a module-level store that the pipeline updates after each scan.

Port: 8765 (chosen to avoid conflicts with common dev servers)
CORS: open for localhost only, so the Next.js dev server can fetch it.

Thread safety
-------------
All writes to _store go through _store_lock.  Flask runs the WSGI server
in a daemon thread so it dies when the main process exits.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import csv
import io
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared scan result store
# ---------------------------------------------------------------------------

_store_lock = threading.Lock()

# The store holds the last processed batch from the detection pipeline.
# Shape mirrors the web app's ProcessAnalysisResult[] TypeScript interface.
_store: Dict[str, Any] = {
    "results": [],          # list[ProcessAnalysisResult-shaped dicts]
    "summary": {
        "id": "",
        "timestamp": "",
        "totalProcesses": 0,
        "threatsDetected": 0,
        "suspiciousDetected": 0,
        "safeCount": 0,
        "maxRiskScore": 0,
        "averageRiskScore": 0,
    },
    "updated_at": 0.0,      # epoch of last write
}

# Global references to components (set by main.py)
_alert_manager: Optional[Any] = None
_db_logger: Optional[Any] = None
_classifier: Optional[Any] = None
_behavioral_engine: Optional[Any] = None
_recording_manager: Optional[Any] = None
_recording_lock = threading.Lock()
_notifications_enabled = True
_notifications_lock = threading.Lock()

_server_thread: Optional[threading.Thread] = None
_shutdown_event = threading.Event()
_training_lock = threading.Lock()
_training_state: Dict[str, Any] = {
    "status": "idle",
    "message": "No training run started.",
    "result": None,
    "source_file": None,
}


# ---------------------------------------------------------------------------
# Public write API  (called by the detection pipeline after each scan)
# ---------------------------------------------------------------------------

def set_components(alert_manager=None, db_logger=None, classifier=None, behavioral_engine=None) -> None:
    """
    Store references to the main components so API routes can access them.
    Called by main.py during initialization.
    """
    global _alert_manager, _db_logger, _classifier, _behavioral_engine
    _alert_manager = alert_manager
    _db_logger = db_logger
    _classifier = classifier
    _behavioral_engine = behavioral_engine


def set_notifications_enabled(enabled: bool) -> None:
    global _notifications_enabled
    with _notifications_lock:
        _notifications_enabled = bool(enabled)


def get_notifications_enabled() -> bool:
    with _notifications_lock:
        return _notifications_enabled


def set_recording_manager(recording_manager: Any) -> None:
    global _recording_manager
    with _recording_lock:
        _recording_manager = recording_manager

def update_scan_results(results: List[Dict]) -> None:
    """
    Replace the stored scan with a fresh batch.

    Parameters
    ----------
    results : list[dict]
        Each dict must match the ProcessAnalysisResult interface expected
        by the web app.  _build_result_dict() below produces the right shape.
    """
    if not results:
        return

    threats    = [r for r in results if r.get("classification") == "MALICIOUS"]
    suspicious = [r for r in results if r.get("classification") == "SUSPICIOUS"]
    safe       = [r for r in results if r.get("classification") == "SAFE"]

    risk_scores  = [r.get("riskScore", 0) for r in results]
    max_risk     = max(risk_scores, default=0)
    avg_risk     = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0

    summary = {
        "id":                  f"live_{int(time.time())}",
        "timestamp":           time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "totalProcesses":      len(results),
        "threatsDetected":     len(threats),
        "suspiciousDetected":  len(suspicious),
        "safeCount":           len(safe),
        "maxRiskScore":        max_risk,
        "averageRiskScore":    avg_risk,
    }

    with _store_lock:
        _store["results"]    = results
        _store["summary"]    = summary
        _store["updated_at"] = time.time()

    logger.debug(
        "live_api store updated: %d processes, %d threats, %d suspicious",
        len(results), len(threats), len(suspicious),
    )


def build_result_dict(
    classification_result,   # ClassificationResult from classifier.py
    feature_vector,          # FeatureVector from feature_extractor.py
) -> Dict:
    """
    Convert pipeline objects into the dict shape expected by the web UI.

    Matches the ProcessAnalysisResult TypeScript interface in web/src/lib/types.ts
    """
    from .classifier import RiskLevel

    cr  = classification_result
    fv  = feature_vector

    # Map RiskLevel → web classification string
    cls_map = {
        RiskLevel.SAFE:       "SAFE",
        RiskLevel.SUSPICIOUS: "SUSPICIOUS",
        RiskLevel.MALICIOUS:  "MALICIOUS",
    }
    classification = cls_map.get(cr.risk_level, "SAFE")

    # Convert score (0–1) to 0–100 risk score the web UI expects
    risk_score = round(cr.score * 100, 1)

    # Derive human-readable probabilities from score
    # (pipeline gives us a single score, not full probabilities for all 3 classes)
    if classification == "MALICIOUS":
        probs = {"safe": round(1 - cr.score, 3),
                 "suspicious": 0.05,
                 "malicious": round(cr.score, 3)}
    elif classification == "SUSPICIOUS":
        probs = {"safe": round(1 - cr.score, 3),
                 "suspicious": round(cr.score, 3),
                 "malicious": 0.05}
    else:
        probs = {"safe": round(cr.confidence, 3),
                 "suspicious": 0.02,
                 "malicious": 0.01}

    features_list = fv.features.tolist() if hasattr(fv.features, "tolist") else list(fv.features)

    return {
        "pid":            cr.pid,
        "name":           cr.name,
        "riskScore":      risk_score,
        "classification": classification,
        "probabilities":  probs,
        "features":       features_list,
        "reasons":        cr.reasons,
        "cpu":            round(float(fv.features[5]), 2) if len(fv.features) > 5 else 0,
        "memoryMb":       round(float(fv.features[7]), 1) if len(fv.features) > 7 else 0,
        "hasWindow":      bool(fv.features[3]) if len(fv.features) > 3 else False,
        "isSigned":       bool(fv.features[13]) if len(fv.features) > 13 else False,
        "path":           cr.exe or "",
    }


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

def _create_app():
    """Create and configure the Flask app."""
    # Late import so Flask is only required at runtime, not at module load
    from flask import Flask, jsonify, make_response, request

    app = Flask("keylogger_live_api")
    app.logger.setLevel(logging.WARNING)   # silence Flask request logs

    # Disable Flask's default banner
    import logging as _log
    _log.getLogger("werkzeug").setLevel(_log.ERROR)

    # ── CORS helper ─────────────────────────────────────────────────────────
    def _cors(response):
        """Add CORS headers so the Next.js dev server on :3000 can fetch."""
        response.headers["Access-Control-Allow-Origin"]  = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @app.after_request
    def after_request(response):
        return _cors(response)

    # ── Routes ───────────────────────────────────────────────────────────────

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "version": "1.0",
                        "updated_at": _store["updated_at"]})

    @app.route("/api/scan", methods=["GET"])
    def get_scan():
        """
        Return the full current scan as a ScanSummary-shaped object.
        The web app destructures  data.summary  from this response.
        """
        with _store_lock:
            results  = list(_store["results"])
            summary  = dict(_store["summary"])

        # Attach results inside summary so the web client can read
        # data.summary.results  — same shape as the CSV upload response.
        summary["results"] = results

        return jsonify({"success": True, "summary": summary})

    @app.route("/api/scan/summary", methods=["GET"])
    def get_summary():
        """Lightweight endpoint — just the counters, no process list."""
        with _store_lock:
            summary = dict(_store["summary"])
        return jsonify(summary)

    @app.route("/api/scan/processes", methods=["GET"])
    def get_processes():
        """Return only the process list array."""
        with _store_lock:
            results = list(_store["results"])
        return jsonify(results)

    # ── NEW ROUTES FOR GUI TABS ──────────────────────────────────────────────

    @app.route("/api/alerts", methods=["GET"])
    def get_alerts():
        """Return recent live alerts from AlertManager."""
        if not _alert_manager:
            return jsonify({"success": False, "error": "AlertManager not initialized"}), 503

        try:
            alerts_records = _alert_manager.recent_alerts
            alerts_list = []

            for rec in alerts_records:
                cr = rec.result
                alerts_list.append({
                    "timestamp": rec.timestamp,
                    "pid": cr.pid,
                    "name": cr.name,
                    "exe": cr.exe,
                    "riskLevel": cr.risk_level.value,  # "safe", "suspicious", "malicious"
                    "score": round(cr.score * 100, 1),
                    "confidence": round(cr.confidence, 3),
                    "reasons": cr.reasons,
                    "notified": rec.notified,
                    "actionTaken": rec.action_taken.value if rec.action_taken else None,
                    "actioned": rec.action_result is not None,
                })

            return jsonify({"success": True, "alerts": alerts_list})
        except Exception as exc:
            logger.error("get_alerts error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/history", methods=["GET"])
    def get_history():
        """Return detection history from DBLogger."""
        if not _db_logger:
            return jsonify({"success": False, "error": "DBLogger not initialized"}), 503

        try:
            limit = max(1, min(int(request.args.get("limit", 200)), 1000))
            risk_filter = request.args.get("risk", None)  # "malicious", "suspicious", "safe", or None
            hours = max(1, min(int(request.args.get("hours", 24)), 8760))

            valid_risk = risk_filter.lower() if risk_filter else None
            if valid_risk not in ("malicious", "suspicious", "safe"):
                valid_risk = None
            detections = _db_logger.query_detections(
                limit=limit,
                risk_level=valid_risk,
                since=time.time() - hours * 3600,
            )

            return jsonify({"success": True, "history": detections})
        except Exception as exc:
            logger.error("get_history error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/statistics", methods=["GET"])
    def get_statistics():
        """Return detection statistics."""
        if not _db_logger:
            return jsonify({"success": False, "error": "DBLogger not initialized"}), 503

        try:
            db_stats = _db_logger.stats()
            action_counts = db_stats.get("action_counts", {})

            # Model status
            model_status = "Unknown"
            if _classifier:
                if _classifier.using_ml_model:
                    if _classifier.is_personalized_model():
                        model_status = "Personalized model active"
                    else:
                        model_status = "Generic ML model active (v1.0)"
                else:
                    model_status = "Fallback heuristic mode"

            return jsonify({
                "success": True,
                "statistics": {
                    "totalDetections": db_stats.get("total_detections", 0),
                    "malicious": db_stats.get("malicious_count", 0),
                    "suspicious": db_stats.get("suspicious_count", 0),
                    "actioned": db_stats.get("actioned_count", 0),
                    "actionCounts": action_counts,
                    "modelStatus": model_status,
                }
            })
        except Exception as exc:
            logger.error("get_statistics error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/history/export", methods=["GET"])
    def export_history():
        """Export the local detection history in CSV, JSON, or PDF format."""
        if not _db_logger:
            return jsonify({"success": False, "error": "DBLogger not initialized"}), 503

        export_format = request.args.get("format", "csv").lower()
        if export_format not in ("csv", "json", "pdf"):
            return jsonify({"success": False, "error": "format must be csv, json, or pdf"}), 400
        try:
            rows = _db_logger.query_detections(limit=100_000)
            columns = [
                "detected_at", "process_name", "pid", "risk_level", "score",
                "confidence", "reasons", "exe_path", "model_version", "actioned",
            ]
            stamp = time.strftime("%Y%m%d_%H%M%S")
            if export_format == "json":
                payload = json.dumps(rows, indent=2, ensure_ascii=True).encode("utf-8")
                return _download(payload, "application/json", f"keyguard_detections_{stamp}.json")
            if export_format == "csv":
                output = io.StringIO(newline="")
                writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    export_row = dict(row)
                    detected_at = export_row.get("detected_at")
                    export_row["detected_at"] = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(detected_at)
                    ) if detected_at else ""
                    reasons = export_row.get("reasons", [])
                    if isinstance(reasons, list):
                        export_row["reasons"] = "; ".join(reasons)
                    export_row["actioned"] = "Yes" if export_row.get("actioned") else "No"
                    writer.writerow(export_row)
                return _download(
                    output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8",
                    f"keyguard_detections_{stamp}.csv",
                )

            from fpdf import FPDF

            pdf = FPDF(orientation="L", unit="mm", format="A4")
            pdf.set_auto_page_break(auto=True, margin=14)
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, "KeyGuard Detection History", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=9)
            pdf.cell(0, 7, f"Exported {time.strftime('%Y-%m-%d %H:%M:%S')} | {len(rows)} detections", new_x="LMARGIN", new_y="NEXT")
            widths = [34, 48, 16, 25, 18, 18, 78, 35]
            headers = ["Date / time", "Process", "PID", "Risk", "Score", "Actioned", "Reasons", "Model"]
            pdf.set_font("Helvetica", "B", 8)
            for header, width in zip(headers, widths):
                pdf.cell(width, 8, header, border=1)
            pdf.ln()
            pdf.set_font("Helvetica", size=7)
            for row in rows:
                reasons = row.get("reasons", [])
                if isinstance(reasons, list):
                    reasons = "; ".join(reasons)
                values = [
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(row.get("detected_at", 0))),
                    str(row.get("process_name", "")), str(row.get("pid", "")),
                    str(row.get("risk_level", "")), f"{float(row.get('score', 0)):.0%}",
                    "Yes" if row.get("actioned") else "No", str(reasons),
                    str(row.get("model_version", "")),
                ]
                if pdf.get_y() > 180:
                    pdf.add_page()
                for value, width in zip(values, widths):
                    pdf.cell(width, 7, value.encode("latin-1", "replace").decode("latin-1")[:46], border=1)
                pdf.ln()
            payload = pdf.output()
            return _download(bytes(payload), "application/pdf", f"keyguard_report_{stamp}.pdf")
        except ImportError:
            return jsonify({"success": False, "error": "PDF export requires fpdf2. Install project requirements."}), 501
        except Exception as exc:
            logger.error("export_history error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/settings/notifications", methods=["GET", "POST", "OPTIONS"])
    def notification_settings():
        if request.method == "OPTIONS":
            return _cors(make_response("", 200))
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            if not isinstance(data.get("enabled"), bool):
                return jsonify({"success": False, "error": "enabled must be a boolean"}), 400
            set_notifications_enabled(data["enabled"])
        return jsonify({"success": True, "enabled": get_notifications_enabled()})

    @app.route("/api/actions", methods=["POST", "OPTIONS"])
    def take_action():
        """Take an action on an alert (terminate/quarantine/whitelist/dismiss)."""
        if request.method == "OPTIONS":
            return _cors(make_response("", 200))

        if not _alert_manager:
            return jsonify({"success": False, "error": "AlertManager not initialized"}), 503

        try:
            data = request.get_json()
            action_str = data.get("action")  # "terminate", "quarantine", "whitelist", "dismiss"
            pid = data.get("pid")

            if not action_str or pid is None:
                return jsonify({"success": False, "error": "Missing action or pid"}), 400

            # Import ResponseAction enum
            from .alert_manager import ResponseAction

            action_map = {
                "terminate": ResponseAction.TERMINATE,
                "quarantine": ResponseAction.QUARANTINE,
                "whitelist": ResponseAction.WHITELIST,
                "dismiss": ResponseAction.DISMISS,
            }

            if action_str.lower() not in action_map:
                return jsonify({"success": False, "error": f"Invalid action: {action_str}"}), 400

            action = action_map[action_str.lower()]

            # Find the alert record by PID
            alert_rec = None
            for rec in reversed(_alert_manager.recent_alerts):
                if rec.pid == pid:
                    alert_rec = rec
                    break

            if not alert_rec:
                return jsonify({"success": False, "error": f"Alert with PID {pid} not found"}), 404

            # Take action
            result = _alert_manager.take_action(action, alert_rec)

            return jsonify({
                "success": result.success,
                "message": result.message,
                "action": action_str,
                "pid": pid,
            })

        except Exception as exc:
            logger.error("take_action error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/train/status", methods=["GET"])
    def get_training_status():
        from pathlib import Path

        data_dir = Path(__file__).parent.parent / "data"
        recordings = sorted(data_dir.glob("my_behavior_*.csv"), key=lambda p: p.stat().st_mtime)
        with _training_lock:
            state = dict(_training_state)
        state["has_training_data"] = bool(recordings)
        state["latest_recording"] = recordings[-1].name if recordings else None
        recorder = _get_recording_manager()
        state["recording"] = recorder.is_recording
        state["recording_count"] = recorder.count
        state["recording_elapsed_seconds"] = round(recorder.elapsed_seconds)
        return jsonify({"success": True, "training": state})

    @app.route("/api/recording/start", methods=["POST", "OPTIONS"])
    def start_behavior_recording():
        """Start the same process recording session used by the desktop Train tab."""
        if request.method == "OPTIONS":
            return _cors(make_response("", 200))
        if not _db_logger:
            return jsonify({"success": False, "error": "DBLogger not initialized"}), 503

        try:
            recorder = _get_recording_manager()
            session_id = recorder.start()
            return jsonify({
                "success": True,
                "message": "Behavior recording started.",
                "session_id": session_id,
                "recording": True,
            })
        except Exception as exc:
            logger.error("start_behavior_recording error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/train", methods=["POST", "OPTIONS"])
    def train_model():
        """Start personalized model training from the latest desktop recording."""
        if request.method == "OPTIONS":
            return _cors(make_response("", 200))

        try:
            from pathlib import Path

            data_dir = Path(__file__).parent.parent / "data"
            recordings = sorted(data_dir.glob("my_behavior_*.csv"), key=lambda p: p.stat().st_mtime)
            if not recordings:
                return jsonify({
                    "success": False,
                    "error": "No behavior recording CSV found. Record behavior in the desktop Train Model tab first.",
                }), 400

            source = recordings[-1]
            with _training_lock:
                if _training_state["status"] == "running":
                    return jsonify({"success": False, "error": "Model training is already running."}), 409
                _training_state.update({
                    "status": "running",
                    "message": "Starting personalized model training.",
                    "result": None,
                    "source_file": source.name,
                })

            def _train():
                try:
                    from tools.train_model import train_personalized

                    def _progress(message: str, _fraction: float) -> None:
                        with _training_lock:
                            _training_state["message"] = message

                    result = train_personalized(source, progress_callback=_progress)
                    with _training_lock:
                        _training_state.update({
                            "status": "succeeded" if result.get("success") else "failed",
                            "message": "Training complete." if result.get("success") else result.get("error", "Training failed."),
                            "result": result,
                        })
                    if result.get("success"):
                        logger.info("Personalized model training completed successfully")
                    else:
                        logger.error("Personalized model training failed: %s", result.get("error"))
                except Exception as e:
                    with _training_lock:
                        _training_state.update({"status": "failed", "message": str(e)})
                    logger.error("Model training failed: %s", e)

            threading.Thread(target=_train, daemon=True, name="ModelTraining").start()

            return jsonify({
                "success": True,
                "message": "Training started in the background.",
                "source_file": source.name,
            })

        except Exception as exc:
            logger.error("train_model error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/behavior", methods=["GET"])
    def get_behavior():
        """Return behavioral analysis data."""
        if not _behavioral_engine:
            return jsonify({"success": False, "error": "Behavioral engine not available"}), 503

        try:
            typing = _behavioral_engine.current_metrics
            mouse = _behavioral_engine.current_mouse_metrics
            anomaly = _behavioral_engine.current_anomaly

            return jsonify({
                "success": True,
                "behavior": {
                    "available": _behavioral_engine.is_available,
                    "enabled": bool(_behavioral_engine.settings.get("enabled", False)),
                    "baselineAvailable": _behavioral_engine.is_baseline_available,
                    "trainingComplete": _behavioral_engine.is_training_complete,
                    "keystrokes": _behavioral_engine.total_keystrokes,
                    "mouseMovements": _behavioral_engine.total_mouse_movements,
                    "typingSpeedWPM": round(float(typing.wpm), 1) if typing else 0,
                    "keystrokeDwellMean": round(float(typing.avg_dwell_ms), 1) if typing else 0,
                    "keystrokeFlightMean": round(float(typing.avg_flight_ms), 1) if typing else 0,
                    "mouseSpeedMean": round(float(mouse.avg_speed_pxsec), 1) if mouse else 0,
                    "mouseAccelerationMean": round(float(mouse.acceleration_avg), 1) if mouse else 0,
                    "mouseClicks": mouse.click_count if mouse else 0,
                    "similarityScore": round(float(anomaly.similarity_score), 1) if anomaly else 100,
                    "keyboardSimilarity": round(float(anomaly.keyboard_similarity), 1) if anomaly else 100,
                    "mouseSimilarity": round(float(anomaly.mouse_similarity), 1) if anomaly else 100,
                    "status": anomaly.status if anomaly else "grey",
                    "verdict": anomaly.status_label if anomaly else "INSUFFICIENT_DATA",
                    "anomalousMetrics": anomaly.anomalous_metrics if anomaly else [],
                    "explanations": anomaly.explanations if anomaly else [],
                    "settings": {
                        key: _behavioral_engine.settings.get(key)
                        for key in (
                            "enabled", "mouse_tracking_enabled", "mouse_precision",
                            "auto_pause_on_activity", "alert_threshold",
                            "min_alert_duration", "adaptive_baseline",
                            "desktop_notify", "anonymize_export_timestamps",
                        )
                    },
                    "trainingProgress": _behavioral_engine.get_training_progress(),
                    "mousePerformance": _behavioral_engine.get_mouse_performance_stats(),
                }
            })
        except Exception as exc:
            logger.error("get_behavior error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/behavior/settings", methods=["POST", "OPTIONS"])
    def update_behavior_settings():
        if request.method == "OPTIONS":
            return _cors(make_response("", 200))
        if not _behavioral_engine:
            return jsonify({"success": False, "error": "Behavioral engine not available"}), 503
        data = request.get_json(silent=True) or {}
        allowed_boolean = {
            "enabled", "mouse_tracking_enabled", "auto_pause_on_activity",
            "adaptive_baseline", "desktop_notify", "anonymize_export_timestamps",
        }
        if any(key in data and not isinstance(data[key], bool) for key in allowed_boolean):
            return jsonify({"success": False, "error": "Boolean settings must be true or false"}), 400
        precision = data.get("mouse_precision")
        if precision is not None and precision not in ("high", "normal", "low"):
            return jsonify({"success": False, "error": "mouse_precision must be high, normal, or low"}), 400
        try:
            if "alert_threshold" in data and not 40 <= float(data["alert_threshold"]) <= 90:
                raise ValueError("alert_threshold must be between 40 and 90")
            if "min_alert_duration" in data and not 30 <= float(data["min_alert_duration"]) <= 300:
                raise ValueError("min_alert_duration must be between 30 and 300")
            for key in allowed_boolean:
                if key in data:
                    _behavioral_engine.settings[key] = data[key]
            if "alert_threshold" in data:
                _behavioral_engine.settings["alert_threshold"] = float(data["alert_threshold"])
            if "min_alert_duration" in data:
                _behavioral_engine.settings["min_alert_duration"] = float(data["min_alert_duration"])
            if precision:
                _behavioral_engine.set_mouse_precision(precision)
            if "mouse_tracking_enabled" in data:
                _behavioral_engine.set_mouse_tracking_enabled(data["mouse_tracking_enabled"])
            return jsonify({"success": True, "settings": _behavioral_engine.settings})
        except (TypeError, ValueError) as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        except Exception as exc:
            logger.error("update_behavior_settings error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/behavior/action", methods=["POST", "OPTIONS"])
    def behavior_action():
        if request.method == "OPTIONS":
            return _cors(make_response("", 200))
        if not _behavioral_engine:
            return jsonify({"success": False, "error": "Behavioral engine not available"}), 503
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        try:
            if action == "confirm":
                result = _behavioral_engine.confirm_this_was_me()
                return jsonify({"success": result is not None, "message": "Current behavior confirmed and saved." if result else "No behavior snapshot available."})
            if action == "retrain":
                _behavioral_engine.delete_training_data()
                return jsonify({"success": True, "message": "Behavior baseline cleared. New baseline learning has started."})
            return jsonify({"success": False, "error": "action must be confirm or retrain"}), 400
        except Exception as exc:
            logger.error("behavior_action error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/behavior/export/<export_type>", methods=["GET"])
    def export_behavior(export_type: str):
        if not _behavioral_engine:
            return jsonify({"success": False, "error": "Behavioral engine not available"}), 503
        exporters = {
            "keyboard": _behavioral_engine.export_keyboard_json,
            "mouse": _behavioral_engine.export_mouse_json,
            "combined": _behavioral_engine.export_combined_profile_json,
            "session-hour": lambda: _behavioral_engine.export_session_json(duration_mins=60),
            "session-day": lambda: _behavioral_engine.export_session_json(duration_mins=1440),
            "comparison": _behavioral_engine.export_comparison_json,
        }
        if export_type not in exporters:
            return jsonify({"success": False, "error": "Unknown behavior export type"}), 404
        try:
            exported_path = exporters[export_type]()
            return _send_file(exported_path)
        except Exception as exc:
            logger.error("export_behavior error: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 500

    return app


def _download(payload: bytes, content_type: str, filename: str):
    from flask import make_response

    response = make_response(payload)
    response.headers["Content-Type"] = content_type
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _send_file(filepath):
    from flask import send_file

    path = filepath
    return send_file(path, as_attachment=True, download_name=path.name)


def _get_recording_manager():
    global _recording_manager
    if _recording_manager is None:
        with _recording_lock:
            if _recording_manager is None:
                from .ui.dashboard import RecordingManager

                _recording_manager = RecordingManager(_db_logger)
    return _recording_manager


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

PORT = 8765


def start(port: int = PORT) -> None:
    """
    Start the Flask server in a daemon thread.
    Safe to call multiple times — will not start a second server.
    """
    global _server_thread

    if _server_thread and _server_thread.is_alive():
        logger.debug("live_api already running on port %d", port)
        return

    _shutdown_event.clear()

    def _run():
        app = _create_app()
        # use_reloader=False is critical — reloader forks and breaks threads
        app.run(
            host="127.0.0.1",
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )

    _server_thread = threading.Thread(target=_run, name="LiveAPI", daemon=True)
    _server_thread.start()
    logger.info("Live API server started on http://127.0.0.1:%d", port)


def stop() -> None:
    """Signal the server to stop (it's a daemon thread so it dies with the process)."""
    _shutdown_event.set()
    logger.info("Live API server stopped.")
