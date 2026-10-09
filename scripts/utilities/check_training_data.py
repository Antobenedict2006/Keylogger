"""Quick script to check behavioral training data"""
import sqlite3
import os
from pathlib import Path

# Get thresholds from environment (same as main app)
MIN_TRAINING_KS = int(os.environ.get("KGAI_BASELINE_KEYSTROKES", "2000"))
MIN_TRAINING_MOUSE = int(os.environ.get("KGAI_BASELINE_MOUSE", "3000"))

# Find database
db_paths = [
    Path('logs/keylogger_events.db'),
    Path('logs/keylogger_events-LAPTOP-J2AVIL85.db'),
]

db_path = None
for p in db_paths:
    if p.exists():
        db_path = p
        break

if not db_path:
    print("❌ Database not found!")
    print("   Expected locations:")
    for p in db_paths:
        print(f"   - {p}")
    exit(1)

print(f"✅ Found database: {db_path}")
print()

# Connect and check tables
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# List tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
print(f"Tables in database: {tables}")
print()

# Check keystroke data
if 'typing_keystrokes' in tables:
    cursor.execute('SELECT COUNT(*) FROM typing_keystrokes')
    ks_count = cursor.fetchone()[0]
    print(f"✅ Keystrokes recorded: {ks_count:,}")
    print(f"   Progress: {(ks_count/MIN_TRAINING_KS)*100:.1f}% (need {MIN_TRAINING_KS:,})")
else:
    print("❌ typing_keystrokes table not found")
    print("   The behavioral engine may not have started properly")
    ks_count = 0

print()

# Check mouse data
if 'typing_mouse_events' in tables:
    cursor.execute('SELECT COUNT(*) FROM typing_mouse_events')
    mouse_count = cursor.fetchone()[0]
    print(f"✅ Mouse events recorded: {mouse_count:,}")
    print(f"   Progress: {(mouse_count/MIN_TRAINING_MOUSE)*100:.1f}% (need {MIN_TRAINING_MOUSE:,})")
else:
    print("❌ typing_mouse_events table not found")
    print("   The behavioral engine may not have started properly")
    mouse_count = 0

print()
print("=" * 60)

# Check if threshold reached
if ks_count >= MIN_TRAINING_KS and mouse_count >= MIN_TRAINING_MOUSE:
    print("🎉 TRAINING COMPLETE!")
    print("   Baseline should be saved automatically")
    print()
    print("   Expected files:")
    print("   - data/typing_baseline.json")
    print("   - data/mouse_baseline.json")
    print("   - data/keyboard_behavior.json")
    print("   - data/mouse_behavior.json")
    print("   - data/behavioral_profile.json")
elif ks_count == 0 and mouse_count == 0:
    print("⚠️  NO DATA RECORDED YET!")
    print()
    print("Possible issues:")
    print("1. Behavioral Analysis tab not opened in the app")
    print("2. pynput listeners not started")
    print("3. Application needs to be restarted")
    print()
    print("Solution:")
    print("1. Make sure the app is running")
    print("2. Open the 'Behavioral Analysis' tab")
    print("3. Type and move your mouse")
    print("4. Wait a few seconds and run this script again")
else:
    print("⏳ Still collecting data...")
    print()
    remaining_ks = max(0, MIN_TRAINING_KS - ks_count)
    remaining_mouse = max(0, MIN_TRAINING_MOUSE - mouse_count)
    print(f"   Keystrokes remaining: {remaining_ks:,}")
    print(f"   Mouse movements remaining: {remaining_mouse:,}")
    print()
    print(f"   Keep using your computer normally!")

conn.close()
