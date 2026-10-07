"""Debug script to understand the Train Model recording feature."""
import sqlite3
from pathlib import Path
from datetime import datetime

db_path = Path(__file__).parent / "logs" / "keylogger_events.db"

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

print("=" * 70)
print("TRAIN MODEL TAB - RECORDING DEBUG")
print("=" * 70)
print()
print("🔍 What gets recorded:")
print("  • ONLY new processes you launch AFTER clicking 'Start Recording'")
print("  • Does NOT record typing/mouse behavior")
print("  • Does NOT record already-running processes")
print()
print("=" * 70)
print("BEHAVIOR_RECORDINGS TABLE (Process Launches):")
print("=" * 70)

# Check if behavior_recordings exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='behavior_recordings'")
if cursor.fetchone():
    # Count total rows
    cursor.execute("SELECT COUNT(*) FROM behavior_recordings")
    total = cursor.fetchone()[0]
    print(f"\nTotal process launches recorded: {total}")
    
    if total > 0:
        # Show recent recordings
        cursor.execute("""
            SELECT recorded_at, process_name, pid, exe_path, session_id
            FROM behavior_recordings
            ORDER BY recorded_at DESC
            LIMIT 20
        """)
        
        print("\nRecent process launches:")
        print("-" * 70)
        for row in cursor.fetchall():
            recorded_at, process_name, pid, exe_path, session_id = row
            dt = datetime.fromtimestamp(recorded_at).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  [{dt}] {process_name} (PID {pid})")
            print(f"    Session: {session_id[:8]}...")
            if exe_path:
                print(f"    Path: {exe_path[:60]}...")
            print()
    else:
        print("\n⚠️  No process launches recorded yet!")
        print("\n💡 To record data:")
        print("  1. Go to 'Train Personalized Model' tab")
        print("  2. Click '▶ Start Recording'")
        print("  3. OPEN NEW APPLICATIONS (Chrome, Notepad, Calculator, etc.)")
        print("  4. The counter should increase as you launch apps")
        print("  5. Click '⏹ Stop Recording' after launching 50+ apps")
        print("  6. CSV file will be saved to data/ folder")
else:
    print("\n❌ behavior_recordings table does NOT exist!")

print()
print("=" * 70)
print("BEHAVIORAL ANALYSIS DATA (Typing/Mouse Patterns):")
print("=" * 70)

# Check typing behavior
cursor.execute("SELECT COUNT(*) FROM typing_behavior")
typing_count = cursor.fetchone()[0]
print(f"\nTyping behavior records: {typing_count}")

# Check mouse behavior
cursor.execute("SELECT COUNT(*) FROM mouse_behavior")
mouse_count = cursor.fetchone()[0]
print(f"Mouse behavior records: {mouse_count}")

print()
print("💡 Behavioral Analysis is DIFFERENT:")
print("  • Records your typing rhythm and mouse movements automatically")
print("  • Goes to 'Behavioral Analysis' tab (not Train Model tab)")
print("  • Saves to data/my_behavior.json when thresholds met")

conn.close()

print()
print("=" * 70)
print("SUMMARY:")
print("=" * 70)
print()
print("You have TWO separate data collection features:")
print()
print("1️⃣  TRAIN PERSONALIZED MODEL TAB:")
print("   • Records NEW process launches (apps you open)")
print("   • Requires you to manually start/stop recording")
print("   • Need to launch 50+ different applications")
print("   • Saves to: data/my_behavior_YYYYMMDD_HHMMSS.csv")
print("   • Used to train ML model for process detection")
print()
print("2️⃣  BEHAVIORAL ANALYSIS TAB:")
print("   • Records typing rhythm + mouse patterns automatically")
print("   • Runs continuously in the background")
print("   • Need 2,000 keystrokes + 3,000 mouse movements")
print("   • Saves to: data/my_behavior.json (+ 4 other JSON files)")
print("   • Used for user biometric authentication")
print()
print("=" * 70)
