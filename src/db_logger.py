"""
db_logger.py
============
SQLite persistence layer for the keylogger detection system.

Tables
------
  detections
      One row per ClassificationResult that is SUSPICIOUS or MALICIOUS.
      Stores all features, score, risk level, reasons, and timestamps.

  actions
      One row per ActionResult (terminate / quarantine / whitelist / dismiss)
      taken by the user in response to a detection.

  process_snapshots
      Rolling log of raw ProcessSnapshot data (all processes, every scan).
      Kept for audit, retraining, and post-incident review.
      Pruned automatically to keep the last SNAPSHOT_RETENTION_DAYS days.

  feature_vectors
      Feature vectors associated with each detection row.
      One-to-one with detections (detection_id foreign key).

Thread safety
-------------
  Uses a single WAL-mode connection per DBLogger instance, guarded by an
  RLock.  All writes go through _execute() which handles retries on SQLITE_BUSY.

Usage::

    db = DBLogger()
    db.log_detection(classification_result, feature_vector)
    db.log_action(action_result)
    db.log_snapshot(process_snapshot)

    rows = db.query_detections(limit=50)
    rows = db.query_actions()
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .alert_manager import ActionResult, ResponseAction
from .classifier import ClassificationResult, RiskLevel
from .feature_extractor import FeatureVector, FEATURE_NAMES
from .monitor import ProcessSnapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

from .paths import DEFAULT_DB_PATH

# Days of raw process snapshots to retain (older rows are pruned on startup)
SNAPSHOT_RETENTION_DAYS: int = 7

# Max retries when the DB is locked
_BUSY_RETRIES: int = 5
_BUSY_SLEEP:   float = 0.1   # seconds between retries


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS detections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pid             INTEGER  NOT NULL,
    process_name    TEXT     NOT NULL,
    exe_path        TEXT,
    risk_level      TEXT     NOT NULL,   -- safe / suspicious / malicious
    score           REAL     NOT NULL,
    confidence      REAL     NOT NULL,
    reasons         TEXT     NOT NULL,   -- JSON array of strings
    model_version   TEXT,
    detected_at     REAL     NOT NULL,   -- Unix epoch float
    actioned        INTEGER  NOT NULL DEFAULT 0  -- 0=pending, 1=actioned
);

CREATE TABLE IF NOT EXISTS actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id    INTEGER REFERENCES detections(id),
    pid             INTEGER  NOT NULL,
    process_name    TEXT     NOT NULL,
    action          TEXT     NOT NULL,   -- terminate / quarantine / whitelist / dismiss
    success         INTEGER  NOT NULL,   -- 0 or 1
    message         TEXT,
    acted_at        REAL     NOT NULL    -- Unix epoch float
);

CREATE TABLE IF NOT EXISTS feature_vectors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id    INTEGER  NOT NULL REFERENCES detections(id),
    features_json   TEXT     NOT NULL,   -- {feature_name: value, ...}
    snapshot_time   REAL     NOT NULL
);

CREATE TABLE IF NOT EXISTS process_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pid             INTEGER  NOT NULL,
    process_name    TEXT     NOT NULL,
    exe_path        TEXT,
    has_hook        INTEGER  NOT NULL DEFAULT 0,
    has_window      INTEGER  NOT NULL DEFAULT 0,
    cpu_percent     REAL,
    mem_rss_mb      REAL,
    net_connections INTEGER,
    has_startup     INTEGER  NOT NULL DEFAULT 0,
    is_system       INTEGER  NOT NULL DEFAULT 0,
    snapshot_time   REAL     NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_detections_pid      ON detections(pid);
CREATE INDEX IF NOT EXISTS idx_detections_risk     ON detections(risk_level);
CREATE INDEX IF NOT EXISTS idx_detections_time     ON detections(detected_at);
CREATE INDEX IF NOT EXISTS idx_actions_detection   ON actions(detection_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_pid       ON process_snapshots(pid);
CREATE INDEX IF NOT EXISTS idx_snapshots_time      ON process_snapshots(snapshot_time);
"""


# ---------------------------------------------------------------------------
# DBLogger
# ---------------------------------------------------------------------------

class DBLogger:
    """
    SQLite-backed event logger for all pipeline outputs.

    Parameters
    ----------
    db_path : Path
        Location of the SQLite database file.  Created on first use.
    log_all_snapshots : bool
        If True, every ProcessSnapshot is written to process_snapshots.
        Disable in resource-constrained environments.
    """

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        log_all_snapshots: bool = False,
    ) -> None:
        self._db_path = Path(db_path)
        self._log_all_snapshots = log_all_snapshots
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def log_detection(
        self,
        result: ClassificationResult,
        fv: Optional[FeatureVector] = None,
    ) -> int:
        """
        Persist a ClassificationResult (SUSPICIOUS or MALICIOUS).
        Optionally also persists the associated FeatureVector.
        Returns the new detection row id.
        """
        row = (
            result.pid,
            result.name,
            result.exe,
            result.risk_level.value,
            result.score,
            result.confidence,
            json.dumps(result.reasons),
            result.model_version,
            result.timestamp,
        )
        detection_id = self._execute(
            """
            INSERT INTO detections
                (pid, process_name, exe_path, risk_level, score,
                 confidence, reasons, model_version, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
            returning_lastrowid=True,
        )

        if fv is not None and detection_id:
            self._execute(
                """
                INSERT INTO feature_vectors (detection_id, features_json, snapshot_time)
                VALUES (?, ?, ?)
                """,
                (
                    detection_id,
                    json.dumps(fv.to_dict()),
                    fv.snapshot_time,
                ),
            )

        logger.debug(
            "Logged detection id=%d pid=%d risk=%s score=%.2f",
            detection_id or -1, result.pid,
            result.risk_level.value, result.score,
        )
        return detection_id or -1

    def log_action(
        self,
        action_result: ActionResult,
        detection_id: Optional[int] = None,
    ) -> None:
        """Persist an ActionResult (user response to an alert)."""
        self._execute(
            """
            INSERT INTO actions
                (detection_id, pid, process_name, action, success, message, acted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                detection_id,
                action_result.pid,
                action_result.name,
                action_result.action.value,
                int(action_result.success),
                action_result.message,
                action_result.timestamp,
            ),
        )
        # Mark associated detection as actioned
        if detection_id:
            self._execute(
                "UPDATE detections SET actioned = 1 WHERE id = ?",
                (detection_id,),
            )
        logger.debug(
            "Logged action: %s pid=%d success=%s",
            action_result.action.value, action_result.pid, action_result.success,
        )

    def log_snapshot(self, snap: ProcessSnapshot) -> None:
        """Persist a raw ProcessSnapshot (used for audit / retraining)."""
        if not self._log_all_snapshots:
            return
        self._execute(
            """
            INSERT INTO process_snapshots
                (pid, process_name, exe_path, has_hook, has_window,
                 cpu_percent, mem_rss_mb, net_connections,
                 has_startup, is_system, snapshot_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snap.pid,
                snap.name,
                snap.exe,
                int(snap.has_ll_keyboard_hook),
                int(snap.has_visible_window),
                snap.cpu_percent,
                snap.mem_rss_mb,
                snap.net_connections,
                int(snap.has_startup_entry),
                int(snap.is_system_process),
                snap.snapshot_time,
            ),
        )

    def log_snapshots_batch(self, snapshots: List[ProcessSnapshot]) -> None:
        """Batch-insert multiple snapshots in a single transaction."""
        if not self._log_all_snapshots or not snapshots:
            return
        rows = [
            (
                s.pid, s.name, s.exe,
                int(s.has_ll_keyboard_hook),
                int(s.has_visible_window),
                s.cpu_percent, s.mem_rss_mb, s.net_connections,
                int(s.has_startup_entry), int(s.is_system_process),
                s.snapshot_time,
            )
            for s in snapshots
        ]
        self._executemany(
            """
            INSERT INTO process_snapshots
                (pid, process_name, exe_path, has_hook, has_window,
                 cpu_percent, mem_rss_mb, net_connections,
                 has_startup, is_system, snapshot_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def query_detections(
        self,
        limit: int = 100,
        risk_level: Optional[str] = None,
        since: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return recent detection rows as dicts.

        Parameters
        ----------
        limit      : max rows to return (most recent first)
        risk_level : filter by 'suspicious' or 'malicious' (None = all)
        since      : Unix epoch; only rows detected after this timestamp
        """
        where_clauses: List[str] = []
        params: List[Any] = []

        if risk_level:
            where_clauses.append("risk_level = ?")
            params.append(risk_level.lower())
        if since:
            where_clauses.append("detected_at >= ?")
            params.append(since)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        params.append(limit)

        rows = self._fetchall(
            f"""
            SELECT id, pid, process_name, exe_path, risk_level, score,
                   confidence, reasons, model_version, detected_at, actioned
            FROM detections
            {where_sql}
            ORDER BY detected_at DESC
            LIMIT ?
            """,
            params,
        )
        return [self._row_to_dict_detections(r) for r in rows]

    def query_actions(
        self,
        limit: int = 100,
        since: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent action rows as dicts."""
        params: List[Any] = []
        where_sql = ""
        if since:
            where_sql = "WHERE acted_at >= ?"
            params.append(since)
        params.append(limit)

        rows = self._fetchall(
            f"""
            SELECT id, detection_id, pid, process_name, action,
                   success, message, acted_at
            FROM actions
            {where_sql}
            ORDER BY acted_at DESC
            LIMIT ?
            """,
            params,
        )
        return [dict(zip(
            ["id","detection_id","pid","process_name","action",
             "success","message","acted_at"], r
        )) for r in rows]

    def query_feature_vector(self, detection_id: int) -> Optional[Dict[str, Any]]:
        """Return the feature vector dict for a given detection_id."""
        rows = self._fetchall(
            "SELECT features_json, snapshot_time FROM feature_vectors WHERE detection_id = ?",
            [detection_id],
        )
        if not rows:
            return None
        features_json, snapshot_time = rows[0]
        return {"features": json.loads(features_json), "snapshot_time": snapshot_time}

    def stats(self) -> Dict[str, Any]:
        """Return summary statistics for the dashboard."""
        rows = self._fetchall(
            """
            SELECT
                COUNT(*) AS total_detections,
                SUM(CASE WHEN risk_level='malicious'  THEN 1 ELSE 0 END) AS malicious_count,
                SUM(CASE WHEN risk_level='suspicious' THEN 1 ELSE 0 END) AS suspicious_count,
                SUM(CASE WHEN actioned=1 THEN 1 ELSE 0 END) AS actioned_count
            FROM detections
            """,
            [],
        )
        total, mal, sus, act = rows[0] if rows else (0, 0, 0, 0)

        action_rows = self._fetchall(
            """
            SELECT action, COUNT(*) FROM actions GROUP BY action
            """,
            [],
        )
        action_counts = {r[0]: r[1] for r in action_rows}

        return {
            "total_detections": total or 0,
            "malicious_count":  mal or 0,
            "suspicious_count": sus or 0,
            "actioned_count":   act or 0,
            "action_counts":    action_counts,
        }

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def prune_old_snapshots(self, retention_days: int = SNAPSHOT_RETENTION_DAYS) -> int:
        """Delete process_snapshots older than retention_days. Returns deleted count."""
        cutoff = time.time() - retention_days * 86400
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "DELETE FROM process_snapshots WHERE snapshot_time < ?", (cutoff,)
            )
            deleted = cur.rowcount
            self._conn.commit()
        if deleted:
            logger.info("Pruned %d old process snapshot rows.", deleted)
        return deleted

    def close(self) -> None:
        """Flush and close the database connection."""
        with self._lock:
            if self._conn:
                try:
                    self._conn.commit()
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
        logger.debug("DBLogger closed.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=10,
            )
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.commit()
        self.prune_old_snapshots()
        logger.info("DBLogger initialised at %s", self._db_path)

    def _execute(
        self,
        sql: str,
        params: Tuple | List = (),
        returning_lastrowid: bool = False,
    ) -> Optional[int]:
        for attempt in range(_BUSY_RETRIES):
            try:
                with self._lock:
                    cur = self._conn.cursor()
                    cur.execute(sql, params)
                    self._conn.commit()
                    return cur.lastrowid if returning_lastrowid else None
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower() and attempt < _BUSY_RETRIES - 1:
                    time.sleep(_BUSY_SLEEP)
                else:
                    logger.error("DB execute error: %s\nSQL: %s", exc, sql.strip())
                    return None
            except Exception as exc:
                logger.error("DB execute error: %s\nSQL: %s", exc, sql.strip())
                return None
        return None

    def _executemany(self, sql: str, rows: List[Tuple]) -> None:
        try:
            with self._lock:
                self._conn.executemany(sql, rows)
                self._conn.commit()
        except Exception as exc:
            logger.error("DB executemany error: %s", exc)

    def _fetchall(self, sql: str, params: List[Any]) -> List[Tuple]:
        try:
            with self._lock:
                cur = self._conn.cursor()
                cur.execute(sql, params)
                return cur.fetchall()
        except Exception as exc:
            logger.error("DB fetchall error: %s\nSQL: %s", exc, sql.strip())
            return []

    @staticmethod
    def _row_to_dict_detections(row: Tuple) -> Dict[str, Any]:
        keys = [
            "id", "pid", "process_name", "exe_path", "risk_level",
            "score", "confidence", "reasons", "model_version",
            "detected_at", "actioned",
        ]
        d = dict(zip(keys, row))
        try:
            d["reasons"] = json.loads(d["reasons"])
        except Exception:
            d["reasons"] = []
        return d

# ===========================================================================
# Behavior Recordings  (added for personalized-model training)
# ===========================================================================

# DDL appended to the existing schema on first use
_BEHAVIOR_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS behavior_recordings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT     NOT NULL,   -- UUID for the recording session
    recorded_at     REAL     NOT NULL,   -- Unix epoch float
    process_name    TEXT     NOT NULL,
    pid             INTEGER  NOT NULL,
    exe_path        TEXT,
    parent_name     TEXT,
    features_json   TEXT     NOT NULL,   -- JSON object {feature_name: value}
    label           TEXT     NOT NULL DEFAULT 'safe'
);

CREATE INDEX IF NOT EXISTS idx_behavior_session
    ON behavior_recordings(session_id);

CREATE INDEX IF NOT EXISTS idx_behavior_time
    ON behavior_recordings(recorded_at);
"""


class BehaviorRecordingStore:
    """
    Thin wrapper around the existing DBLogger connection that persists
    behavior-recording rows for the Train-Model feature.

    Shares the same SQLite connection and RLock as the parent DBLogger so
    all writes are serialized with the rest of the pipeline.

    Usage::

        store = BehaviorRecordingStore(db_logger)
        store.ensure_schema()

        store.save_recorded_process(session_id, process_data, features_dict)

        df = store.export_to_dataframe(session_id)
        store.export_to_csv(session_id, Path("data/my_behavior.csv"))

        count = store.count_for_session(session_id)
        store.delete_session(session_id)
    """

    def __init__(self, db_logger: "DBLogger") -> None:
        # Borrow the connection and lock from the parent DBLogger so we
        # never need a second connection to the same WAL-mode file.
        self._db = db_logger

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        """Create the behavior_recordings table if it does not yet exist."""
        try:
            with self._db._lock:
                self._db._conn.executescript(_BEHAVIOR_SCHEMA_SQL)
                self._db._conn.commit()
            logger.debug("BehaviorRecordingStore schema ensured.")
        except Exception as exc:
            logger.error("BehaviorRecordingStore schema error: %s", exc)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_recorded_process(
        self,
        session_id: str,
        process_data: Dict[str, Any],
        features: Dict[str, float],
        label: str = "safe",
    ) -> None:
        """
        Persist one recorded process row.

        Parameters
        ----------
        session_id   : UUID string identifying the recording session.
        process_data : dict with keys: name, pid, exe_path, parent_name.
        features     : {feature_name: value} for all 24 pipeline features.
        label        : always "safe" for user-launched processes.
        """
        self._db._execute(
            """
            INSERT INTO behavior_recordings
                (session_id, recorded_at, process_name, pid,
                 exe_path, parent_name, features_json, label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                time.time(),
                process_data.get("name", ""),
                process_data.get("pid", 0),
                process_data.get("exe_path") or "",
                process_data.get("parent_name") or "",
                json.dumps(features),
                label,
            ),
        )

    # ------------------------------------------------------------------
    # Read / export
    # ------------------------------------------------------------------

    def count_for_session(self, session_id: str) -> int:
        """Return the number of rows stored for *session_id*."""
        rows = self._db._fetchall(
            "SELECT COUNT(*) FROM behavior_recordings WHERE session_id = ?",
            [session_id],
        )
        return int(rows[0][0]) if rows else 0

    def count_all(self) -> int:
        """Return total rows across all sessions."""
        rows = self._db._fetchall(
            "SELECT COUNT(*) FROM behavior_recordings", []
        )
        return int(rows[0][0]) if rows else 0

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        Return a summary list of recording sessions ordered newest-first.

        Each entry: {session_id, sample_count, started_at, ended_at}
        """
        rows = self._db._fetchall(
            """
            SELECT session_id,
                   COUNT(*)   AS sample_count,
                   MIN(recorded_at) AS started_at,
                   MAX(recorded_at) AS ended_at
            FROM behavior_recordings
            GROUP BY session_id
            ORDER BY MAX(recorded_at) DESC
            """,
            [],
        )
        return [
            {
                "session_id":   r[0],
                "sample_count": r[1],
                "started_at":   r[2],
                "ended_at":     r[3],
            }
            for r in rows
        ]

    def export_to_dataframe(self, session_id: Optional[str] = None):
        """
        Return a pandas DataFrame of recorded rows, optionally filtered
        to *session_id*.

        Columns: timestamp, process_name, pid, exe_path, parent_name,
                 <24 feature columns>, label
        """
        try:
            import pandas as pd  # local import — keep top-level lean
        except ImportError:
            raise RuntimeError(
                "pandas is required for export_to_dataframe. "
                "Install it with: pip install pandas"
            )

        if session_id:
            rows = self._db._fetchall(
                """
                SELECT recorded_at, process_name, pid, exe_path,
                       parent_name, features_json, label
                FROM behavior_recordings
                WHERE session_id = ?
                ORDER BY recorded_at
                """,
                [session_id],
            )
        else:
            rows = self._db._fetchall(
                """
                SELECT recorded_at, process_name, pid, exe_path,
                       parent_name, features_json, label
                FROM behavior_recordings
                ORDER BY recorded_at
                """,
                [],
            )

        if not rows:
            return pd.DataFrame()

        records = []
        for (recorded_at, proc_name, pid, exe_path,
             parent_name, features_json, label) in rows:
            try:
                feats = json.loads(features_json)
            except Exception:
                feats = {}
            row = {
                "timestamp":    time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(recorded_at)
                ),
                "process_name": proc_name,
                "pid":          pid,
                "exe_path":     exe_path or "",
                "parent_name":  parent_name or "",
            }
            row.update(feats)
            row["label"] = label
            records.append(row)

        return pd.DataFrame(records)

    def export_to_csv(
        self,
        filepath: Path,
        session_id: Optional[str] = None,
    ) -> int:
        """
        Write recorded rows to *filepath* as a CSV.

        Returns the number of rows written.
        Raises RuntimeError if pandas is not available or no rows exist.
        """
        df = self.export_to_dataframe(session_id=session_id)
        if df.empty:
            raise RuntimeError("No behavior recordings found to export.")

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(filepath, index=False)
        logger.info(
            "Exported %d behavior-recording rows to %s", len(df), filepath
        )
        return len(df)

    def delete_session(self, session_id: str) -> int:
        """Delete all rows for *session_id*. Returns deleted count."""
        rows_before = self.count_for_session(session_id)
        self._db._execute(
            "DELETE FROM behavior_recordings WHERE session_id = ?",
            (session_id,),
        )
        logger.info(
            "Deleted %d behavior-recording rows for session %s",
            rows_before, session_id,
        )
        return rows_before


# ===========================================================================
# Typing & Mouse Behavior Store  (Phase 1 & 2 — Behavioral Biometrics)
# ===========================================================================

_TYPING_BEHAVIOR_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS typing_behavior (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP,
    recorded_at         REAL     NOT NULL,
    wpm                 REAL,
    avg_dwell_ms        REAL,
    avg_flight_ms       REAL,
    consistency_stddev  REAL,
    burst_count         INTEGER,
    keystroke_count     INTEGER,
    is_training_data    BOOLEAN  DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mouse_behavior (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp                   DATETIME DEFAULT CURRENT_TIMESTAMP,
    recorded_at                 REAL     NOT NULL,
    avg_speed_pxsec             REAL,
    curvature_index             REAL,
    micro_movements_per_sec     REAL,
    jitter_stddev_px            REAL,
    avg_click_duration_ms       REAL,
    avg_double_click_ms         REAL,
    click_to_move_latency_ms    REAL,
    pause_frequency_per_min     INTEGER,
    acceleration_avg            REAL,
    scroll_lines_per_scroll     REAL,
    overshoot_frequency         REAL,
    left_right_click_ratio      REAL,
    is_training_data            BOOLEAN  DEFAULT 1
);

CREATE TABLE IF NOT EXISTS behavioral_alerts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           DATETIME DEFAULT CURRENT_TIMESTAMP,
    alerted_at          REAL     NOT NULL,
    similarity_score    REAL,
    duration_seconds    INTEGER,
    wpm_current         REAL,
    wpm_baseline        REAL,
    wpm_zscore          REAL,
    dwell_current       REAL,
    dwell_baseline      REAL,
    consistency_stddev  REAL,
    alert_type          TEXT,
    explanations_json   TEXT,
    user_feedback       TEXT
);

CREATE INDEX IF NOT EXISTS idx_typing_behavior_time
    ON typing_behavior(recorded_at);

CREATE INDEX IF NOT EXISTS idx_mouse_behavior_time
    ON mouse_behavior(recorded_at);

CREATE INDEX IF NOT EXISTS idx_behavioral_alerts_time
    ON behavioral_alerts(alerted_at);
"""


class TypingBehaviorStore:
    """
    Thin wrapper around an existing DBLogger connection that persists
    typing and mouse behavior samples and behavioral alerts for
    Behavioral Biometrics (Phase 1 & 2).

    All timing & motion data is stored without screen/key content (privacy-safe).

    Usage::

        store = TypingBehaviorStore(db_logger)
        store.ensure_schema()

        store.log_typing_sample(metrics)
        store.log_mouse_sample(mouse_metrics)
        store.log_behavioral_alert(anomaly, metrics)
        rows = store.query_recent_samples(limit=100)
    """

    def __init__(self, db_logger: "DBLogger") -> None:
        self._db = db_logger

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        """Create typing_behavior, mouse_behavior and behavioral_alerts tables if absent."""
        try:
            with self._db._lock:
                self._db._conn.executescript(_TYPING_BEHAVIOR_SCHEMA_SQL)
                self._db._conn.commit()
            logger.debug("TypingBehaviorStore schema ensured.")
        except Exception as exc:
            logger.error("TypingBehaviorStore schema error: %s", exc)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def log_typing_sample(self, metrics, is_training: bool = True) -> None:
        """
        Persist one 60-second TypingMetrics window to the database.
        Only timing numbers are stored — no key content.
        """
        self._db._execute(
            """
            INSERT INTO typing_behavior
                (recorded_at, wpm, avg_dwell_ms, avg_flight_ms,
                 consistency_stddev, burst_count, keystroke_count, is_training_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                round(float(getattr(metrics, "wpm", 0.0)), 3),
                round(float(getattr(metrics, "avg_dwell_ms", 0.0)), 3),
                round(float(getattr(metrics, "avg_flight_ms", 0.0)), 3),
                round(float(getattr(metrics, "consistency_stddev", 0.0)), 3),
                int(getattr(metrics, "burst_count", 0)),
                int(getattr(metrics, "keystroke_count", 0)),
                int(is_training),
            ),
        )

    def log_mouse_sample(self, metrics, is_training: bool = True) -> None:
        """
        Persist one 60-second MouseMetrics window to the database.
        Only motion metrics are stored — no screen content.
        """
        self._db._execute(
            """
            INSERT INTO mouse_behavior
                (recorded_at, avg_speed_pxsec, curvature_index,
                 micro_movements_per_sec, jitter_stddev_px,
                 avg_click_duration_ms, avg_double_click_ms,
                 click_to_move_latency_ms, pause_frequency_per_min,
                 acceleration_avg, scroll_lines_per_scroll,
                 overshoot_frequency, left_right_click_ratio, is_training_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                round(float(getattr(metrics, "avg_speed_pxsec", 0.0)), 3),
                round(float(getattr(metrics, "curvature_index", 1.0)), 3),
                round(float(getattr(metrics, "micro_movements_per_sec", 0.0)), 3),
                round(float(getattr(metrics, "jitter_stddev_px", 0.0)), 3),
                round(float(getattr(metrics, "avg_click_duration_ms", 0.0)), 3),
                round(float(getattr(metrics, "avg_double_click_ms", 0.0)), 3),
                round(float(getattr(metrics, "click_to_move_latency_ms", 0.0)), 3),
                int(getattr(metrics, "pause_frequency_per_min", 0)),
                round(float(getattr(metrics, "acceleration_avg", 0.0)), 3),
                round(float(getattr(metrics, "scroll_lines_per_scroll", 0.0)), 3),
                round(float(getattr(metrics, "overshoot_frequency", 0.0)), 3),
                round(float(getattr(metrics, "left_right_click_ratio", 15.0)), 3),
                int(is_training),
            ),
        )

    def log_behavioral_alert(self, anomaly, metrics=None) -> None:
        """Persist a detected anomaly alert row."""
        alert_type = (
            getattr(anomaly, "bot_type", None) or
            ("bot_detected" if getattr(anomaly, "bot_detected", False) else "human_different")
        )
        wpm_z = getattr(anomaly, "z_scores", {}).get("wpm", 0.0) if hasattr(anomaly, "z_scores") else 0.0
        wpm_cur = round(float(getattr(metrics, "wpm", 0.0)), 3) if metrics else 0.0
        dwell_cur = round(float(getattr(metrics, "avg_dwell_ms", 0.0)), 3) if metrics else 0.0
        cons_cur = round(float(getattr(metrics, "consistency_stddev", 0.0)), 3) if metrics else 0.0

        self._db._execute(
            """
            INSERT INTO behavioral_alerts
                (alerted_at, similarity_score, wpm_current, wpm_zscore,
                 dwell_current, consistency_stddev, alert_type, explanations_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                round(float(getattr(anomaly, "similarity_score", 0.0)), 2),
                wpm_cur,
                round(wpm_z, 3),
                dwell_cur,
                cons_cur,
                str(alert_type),
                json.dumps(getattr(anomaly, "explanations", [])),
            ),
        )

    def update_alert_feedback(self, alert_id: int, feedback: str) -> None:
        """
        Record user feedback on an alert row.
        feedback: 'this_was_me' | 'confirmed_threat' | 'dismissed'
        """
        self._db._execute(
            "UPDATE behavioral_alerts SET user_feedback = ? WHERE id = ?",
            (feedback, alert_id),
        )

    def delete_all_samples(self) -> None:
        """Delete all typing_behavior and mouse_behavior rows."""
        self._db._execute("DELETE FROM typing_behavior", ())
        try:
            self._db._execute("DELETE FROM mouse_behavior", ())
        except Exception:
            pass
        logger.info("All typing_behavior and mouse_behavior rows deleted.")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query_recent_samples(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent typing samples ordered newest-first."""
        rows = self._db._fetchall(
            """
            SELECT id, recorded_at, wpm, avg_dwell_ms, avg_flight_ms,
                   consistency_stddev, burst_count, keystroke_count, is_training_data
            FROM typing_behavior
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            [limit],
        )
        keys = [
            "id", "recorded_at", "wpm", "avg_dwell_ms", "avg_flight_ms",
            "consistency_stddev", "burst_count", "keystroke_count", "is_training_data",
        ]
        return [dict(zip(keys, r)) for r in rows]

    def query_recent_mouse_samples(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent mouse samples ordered newest-first."""
        rows = self._db._fetchall(
            """
            SELECT id, recorded_at, avg_speed_pxsec, curvature_index,
                   micro_movements_per_sec, jitter_stddev_px,
                   avg_click_duration_ms, avg_double_click_ms,
                   click_to_move_latency_ms, pause_frequency_per_min,
                   acceleration_avg, scroll_lines_per_scroll,
                   overshoot_frequency, left_right_click_ratio, is_training_data
            FROM mouse_behavior
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            [limit],
        )
        keys = [
            "id", "recorded_at", "avg_speed_pxsec", "curvature_index",
            "micro_movements_per_sec", "jitter_stddev_px",
            "avg_click_duration_ms", "avg_double_click_ms",
            "click_to_move_latency_ms", "pause_frequency_per_min",
            "acceleration_avg", "scroll_lines_per_scroll",
            "overshoot_frequency", "left_right_click_ratio", "is_training_data",
        ]
        return [dict(zip(keys, r)) for r in rows]

    def get_training_sample_count(self) -> int:
        """Return the number of typing training-tagged rows."""
        rows = self._db._fetchall(
            "SELECT COUNT(*) FROM typing_behavior WHERE is_training_data = 1", []
        )
        return int(rows[0][0]) if rows else 0

    def get_mouse_training_sample_count(self) -> int:
        """Return the number of mouse training-tagged rows."""
        rows = self._db._fetchall(
            "SELECT COUNT(*) FROM mouse_behavior WHERE is_training_data = 1", []
        )
        return int(rows[0][0]) if rows else 0

    def query_recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent behavioral alerts ordered newest-first."""
        rows = self._db._fetchall(
            """
            SELECT id, alerted_at, similarity_score, wpm_current,
                   dwell_current, consistency_stddev, alert_type,
                   explanations_json, user_feedback
            FROM behavioral_alerts
            ORDER BY alerted_at DESC
            LIMIT ?
            """,
            [limit],
        )
        keys = [
            "id", "alerted_at", "similarity_score", "wpm_current",
            "dwell_current", "consistency_stddev", "alert_type",
            "explanations_json", "user_feedback",
        ]
        result = []
        for r in rows:
            d = dict(zip(keys, r))
            try:
                d["explanations"] = json.loads(d.pop("explanations_json", "[]"))
            except Exception:
                d["explanations"] = []
            result.append(d)
        return result


# Alias for multi-modal behavioral storage
BehavioralStore = TypingBehaviorStore
