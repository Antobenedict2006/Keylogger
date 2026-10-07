"""Manually export the existing recording session to CSV."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.db_logger import DBLogger

# Initialize database
db_path = Path(__file__).parent / "logs" / "keylogger_events.db"
db = DBLogger(str(db_path))

# Import the recording store
from src.db_logger import BehaviorRecordingStore
store = BehaviorRecordingStore(db)
store.ensure_schema()

# List all sessions
sessions = store.list_sessions()
print("=" * 70)
print("AVAILABLE RECORDING SESSIONS:")
print("=" * 70)

if not sessions:
    print("\n❌ No recording sessions found in database!")
    print("\nThis means when you clicked 'Start Recording', either:")
    print("  • No new applications were launched")
    print("  • The app wasn't properly initialized")
    print("  • The recording feature failed silently")
    sys.exit(1)

for i, session in enumerate(sessions, 1):
    from datetime import datetime
    start_dt = datetime.fromtimestamp(session['started_at'])
    end_dt = datetime.fromtimestamp(session['ended_at'])
    
    print(f"\n{i}. Session ID: {session['session_id'][:20]}...")
    print(f"   Samples: {session['sample_count']}")
    print(f"   Date: {start_dt.strftime('%Y-%m-%d')}")
    print(f"   Time: {start_dt.strftime('%H:%M:%S')} - {end_dt.strftime('%H:%M:%S')}")

print("\n" + "=" * 70)
print("EXPORTING ALL SESSIONS TO CSV:")
print("=" * 70)

output_dir = Path(__file__).parent / "data"
output_dir.mkdir(exist_ok=True)

for session in sessions:
    session_id = session['session_id']
    start_dt = datetime.fromtimestamp(session['started_at'])
    
    # Generate filename
    csv_filename = f"my_behavior_{start_dt.strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = output_dir / csv_filename
    
    try:
        rows_written = store.export_to_csv(csv_path, session_id=session_id)
        print(f"\n✅ Exported {rows_written} rows to:")
        print(f"   {csv_path}")
    except Exception as exc:
        print(f"\n❌ Export failed for session {session_id[:12]}...")
        print(f"   Error: {exc}")

print("\n" + "=" * 70)
print("DONE!")
print("=" * 70)
