"""
test_ui.py
==========
Quick UI test script to verify the modernized dashboard without running the full application.

This script creates a minimal mock environment to test the UI visually.

Usage:
    python test_ui.py
"""

import tkinter as tk
from tkinter import ttk
from src.ui.dashboard import Dashboard, C
import time
from pathlib import Path
import sqlite3


class MockAlertManager:
    """Mock AlertManager for testing."""
    def __init__(self):
        self.recent_alerts = []
        self._action_callback = None
    
    def clear_alerts(self):
        self.recent_alerts = []
    
    def take_action(self, action, record):
        class Result:
            success = True
            message = f"Mock: Action {action} completed"
        return Result()


class MockDBLogger:
    """Mock database for testing."""
    def __init__(self):
        self._db_path = Path("test_ui.db")
        self._create_test_db()
    
    def _create_test_db(self):
        """Create a temporary test database with sample data."""
        conn = sqlite3.connect(str(self._db_path))
        cur = conn.cursor()
        
        # Create tables
        cur.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY,
                pid INTEGER,
                process_name TEXT,
                exe_path TEXT,
                risk_level TEXT,
                score REAL,
                confidence REAL,
                reasons TEXT,
                model_version TEXT,
                detected_at REAL,
                actioned INTEGER
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY,
                detection_id INTEGER,
                pid INTEGER,
                process_name TEXT,
                action TEXT,
                success INTEGER,
                message TEXT,
                acted_at REAL
            )
        """)
        
        # Insert sample data
        now = time.time()
        sample_data = [
            (1234, "suspicious_app.exe", "C:\\Apps\\suspicious_app.exe", "malicious", 0.92, 0.88, '["Hook detected", "Hidden window"]', "v1.0", now - 3600, 1),
            (5678, "keylogger.exe", "C:\\Temp\\keylogger.exe", "malicious", 0.95, 0.91, '["Low-level keyboard hook", "No visible window", "Startup entry"]', "v1.0", now - 7200, 0),
            (9101, "monitor_tool.exe", "C:\\Tools\\monitor.exe", "suspicious", 0.65, 0.72, '["Hook detected"]', "v1.0", now - 1800, 0),
            (1121, "dev_tool.exe", "C:\\Dev\\tool.exe", "suspicious", 0.58, 0.65, '["Hook detected"]', "v1.0", now - 900, 1),
        ]
        
        for i in range(40):  # Add more sample data
            cur.execute("""
                INSERT INTO detections 
                (pid, process_name, exe_path, risk_level, score, confidence, reasons, model_version, detected_at, actioned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, sample_data[i % len(sample_data)])
        
        # Sample actions
        cur.execute("""
            INSERT INTO actions (detection_id, pid, process_name, action, success, message, acted_at)
            VALUES (1, 1234, 'suspicious_app.exe', 'terminate', 1, 'Process terminated successfully', ?)
        """, (now - 3500,))
        
        cur.execute("""
            INSERT INTO actions (detection_id, pid, process_name, action, success, message, acted_at)
            VALUES (4, 1121, 'dev_tool.exe', 'whitelist', 1, 'Added to whitelist', ?)
        """, (now - 800,))
        
        conn.commit()
        conn.close()
    
    def query_detections(self, limit=100, risk_level=None, since=None):
        """Query detections from test database."""
        conn = sqlite3.connect(str(self._db_path))
        cur = conn.cursor()
        
        query = "SELECT id, pid, process_name, exe_path, risk_level, score, confidence, reasons, model_version, detected_at, actioned FROM detections"
        params = []
        where_clauses = []
        
        if risk_level:
            where_clauses.append("risk_level = ?")
            params.append(risk_level.lower())
        if since:
            where_clauses.append("detected_at >= ?")
            params.append(since)
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "pid": row[1],
                "process_name": row[2],
                "exe_path": row[3],
                "risk_level": row[4],
                "score": row[5],
                "confidence": row[6],
                "reasons": row[7],
                "model_version": row[8],
                "detected_at": row[9],
                "actioned": row[10],
            })
        return result
    
    def query_actions(self, limit=100, since=None):
        """Query actions from test database."""
        conn = sqlite3.connect(str(self._db_path))
        cur = conn.cursor()
        
        query = "SELECT id, detection_id, pid, process_name, action, success, message, acted_at FROM actions"
        params = []
        
        if since:
            query += " WHERE acted_at >= ?"
            params.append(since)
        
        query += " ORDER BY acted_at DESC LIMIT ?"
        params.append(limit)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "detection_id": row[1],
                "pid": row[2],
                "process_name": row[3],
                "action": row[4],
                "success": row[5],
                "message": row[6],
                "acted_at": row[7],
            })
        return result
    
    def stats(self):
        """Get statistics from test database."""
        conn = sqlite3.connect(str(self._db_path))
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM detections")
        total = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM detections WHERE risk_level='malicious'")
        malicious = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM detections WHERE risk_level='suspicious'")
        suspicious = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM detections WHERE actioned=1")
        actioned = cur.fetchone()[0]
        
        cur.execute("SELECT action, COUNT(*) FROM actions GROUP BY action")
        action_rows = cur.fetchall()
        action_counts = {row[0]: row[1] for row in action_rows}
        
        conn.close()
        
        return {
            "total_detections": total,
            "malicious_count": malicious,
            "suspicious_count": suspicious,
            "actioned_count": actioned,
            "action_counts": action_counts,
        }
    
    def close(self):
        """Clean up test database."""
        try:
            self._db_path.unlink()
        except:
            pass


def main():
    """Run UI test."""
    print("=" * 60)
    print("  UI Test Mode - Modernized Dashboard with Menu Bar")
    print("=" * 60)
    print()
    print("This will open the dashboard with mock data.")
    print("Test the following features:")
    print("  1. Navigate between tabs")
    print("  2. Click Statistics cards (should filter History)")
    print("  3. Check modern styling (light theme, hover effects)")
    print("  4. Test filter controls in History tab")
    print("  5. Double-click rows for detail popups")
    print("  6. ⭐ NEW: Test menu bar (File, View, Tools, Help)")
    print("  7. ⭐ NEW: Toggle notifications (View → Show Notifications)")
    print("  8. ⭐ NEW: Open Settings dialog (Tools → Settings)")
    print("  9. ⭐ NEW: Try keyboard shortcuts (Esc, F5)")
    print()
    print("Press Ctrl+C or close the window to exit.")
    print("=" * 60)
    print()
    
    # Create mock objects
    alert_mgr = MockAlertManager()
    db_logger = MockDBLogger()
    
    def get_model_status():
        return "✓ ML model active (test mode) | 0 scans | 0 threats"
    
    def on_pause(paused):
        print(f"{'Paused' if paused else 'Resumed'} monitoring")
    
    def on_quit():
        print("Quitting test UI...")
        db_logger.close()
    
    # Create and run dashboard
    try:
        dashboard = Dashboard(
            alert_manager=alert_mgr,
            db_logger=db_logger,
            get_model_status=get_model_status,
            on_pause=on_pause,
            on_quit=on_quit,
        )
        dashboard.run()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db_logger.close()
        print("\nTest completed. Test database cleaned up.")


if __name__ == "__main__":
    main()
