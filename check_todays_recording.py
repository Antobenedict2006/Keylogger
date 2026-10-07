"""Check if today's recording is in the database but not exported."""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

db_path = Path(__file__).parent / "logs" / "keylogger_events.db"

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Get today's date range
today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
today_start_ts = today_start.timestamp()

print("=" * 70)
print(f"CHECKING FOR TODAY'S RECORDINGS ({datetime.now().strftime('%Y-%m-%d')})")
print("=" * 70)
print()

# Get all sessions with their dates
cursor.execute("""
    SELECT session_id,
           COUNT(*) AS sample_count,
           MIN(recorded_at) AS started_at,
           MAX(recorded_at) AS ended_at
    FROM behavior_recordings
    GROUP BY session_id
    ORDER BY MAX(recorded_at) DESC
""")

sessions = cursor.fetchall()

print(f"Total sessions found: {len(sessions)}")
print()

today_sessions = []
for session_id, count, start_ts, end_ts in sessions:
    start_dt = datetime.fromtimestamp(start_ts)
    end_dt = datetime.fromtimestamp(end_ts)
    
    is_today = start_ts >= today_start_ts
    
    print(f"Session: {session_id[:16]}...")
    print(f"  Samples: {count}")
    print(f"  Started: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Ended:   {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  {'✅ TODAY' if is_today else '📅 ' + start_dt.strftime('%b %d')}")
    print()
    
    if is_today:
        today_sessions.append((session_id, count, start_dt, end_dt))

if today_sessions:
    print("=" * 70)
    print(f"✅ FOUND {len(today_sessions)} SESSION(S) FROM TODAY!")
    print("=" * 70)
    print()
    
    for session_id, count, start_dt, end_dt in today_sessions:
        print(f"Session ID: {session_id}")
        print(f"Process count: {count}")
        print(f"Recording time: {start_dt.strftime('%H:%M:%S')} - {end_dt.strftime('%H:%M:%S')}")
        print()
        
        # Check if CSV exists
        expected_csv = Path(__file__).parent / "data" / f"my_behavior_{start_dt.strftime('%Y%m%d_%H%M%S')}.csv"
        expected_csv2 = Path(__file__).parent / "data" / f"my_behavior_{end_dt.strftime('%Y%m%d_%H%M%S')}.csv"
        
        csv_exists = expected_csv.exists() or expected_csv2.exists()
        
        if csv_exists:
            print(f"  ✅ CSV file exists:")
            if expected_csv.exists():
                print(f"     {expected_csv.name}")
            if expected_csv2.exists():
                print(f"     {expected_csv2.name}")
        else:
            print(f"  ❌ CSV NOT FOUND! Expected:")
            print(f"     {expected_csv.name}")
            print(f"     or")
            print(f"     {expected_csv2.name}")
            print()
            print(f"  🔧 I can export this session for you!")
        print()
        
        # Show some sample processes
        cursor.execute("""
            SELECT process_name, COUNT(*) as count
            FROM behavior_recordings
            WHERE session_id = ?
            GROUP BY process_name
            ORDER BY count DESC
            LIMIT 10
        """, (session_id,))
        
        print("  Top processes recorded:")
        for proc_name, proc_count in cursor.fetchall():
            print(f"    • {proc_name}: {proc_count}x")
        print()
else:
    print("=" * 70)
    print("❌ NO RECORDINGS FROM TODAY")
    print("=" * 70)
    print()
    print("Possible reasons:")
    print("  • You clicked Stop Recording but no new apps were launched")
    print("  • The recording counter showed 0")
    print("  • An error occurred during recording")

conn.close()

print()
print("=" * 70)
print("EXISTING CSV FILES:")
print("=" * 70)
data_dir = Path(__file__).parent / "data"
csv_files = sorted(data_dir.glob("my_behavior_*.csv"))
if csv_files:
    for csv in csv_files:
        size_kb = csv.stat().st_size / 1024
        mod_time = datetime.fromtimestamp(csv.stat().st_mtime)
        print(f"  • {csv.name} ({size_kb:.1f} KB) - {mod_time.strftime('%Y-%m-%d %H:%M')}")
else:
    print("  (none)")
