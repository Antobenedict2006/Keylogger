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

DEFAULT_DB_PATH = Path(__file__).parent.parent / "logs" / "keylogger_events.db"

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
