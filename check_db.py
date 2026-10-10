import sqlite3
conn = sqlite3.connect(r"C:\Users\Anto\AppData\Local\KeyloggerDetector\logs\keylogger_events.db")
cur = conn.cursor()

print("=== Total row counts ===")
cur.execute("SELECT COUNT(*) FROM process_snapshots")
print("process_snapshots rows:", cur.fetchone())
cur.execute("SELECT COUNT(*) FROM detections")
print("detections rows:", cur.fetchone())

print()
print("=== Most recent 15 process_snapshots (any process) ===")
cur.execute("SELECT process_name, is_system, snapshot_time FROM process_snapshots ORDER BY snapshot_time DESC LIMIT 15")
for row in cur.fetchall():
    print(row)

print()
print("=== Distinct is_system values and counts ===")
cur.execute("SELECT is_system, COUNT(*) FROM process_snapshots GROUP BY is_system")
for row in cur.fetchall():
    print(row)
