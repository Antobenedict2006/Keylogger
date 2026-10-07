# Train Model Recording - Troubleshooting Guide

## Problem: CSV Not Saving After Stop Recording

### Root Cause
The "Train Personalized Model" tab **ONLY records NEW applications you launch AFTER clicking Start Recording**.

If you don't open any new apps during recording, the counter stays at 0 and no CSV is saved.

---

## How the Recording Feature Works

1. **Click "▶ Start Recording"**
   - Takes a snapshot of all currently running processes
   - Starts monitoring for NEW processes

2. **Launch Applications**
   - Open Chrome, Notepad, Calculator, Excel, games, etc.
   - Each NEW app increases the counter
   - **Already-running apps are NOT counted**

3. **Click "⏹ Stop Recording"**
   - If counter = 0: Shows warning, no CSV saved
   - If counter < 50: Shows warning, CSV saved but can't train yet
   - If counter ≥ 50: CSV saved, can train model

---

## Why Your Recording Didn't Save

**Most likely**: You clicked Start → Stop without opening any NEW applications during that time.

The feature doesn't record:
- ❌ Applications already running when you clicked Start
- ❌ Your typing or mouse movements (that's a different tab)
- ❌ Background system processes

It ONLY records:
- ✅ NEW applications you manually launch after clicking Start

---

## How to Successfully Record

### Option 1: Quick Test (5 minutes)
```
1. Click "▶ Start Recording"
2. Open 50+ different applications:
   - Chrome (counts as 1)
   - Notepad (counts as 1)
   - Calculator (counts as 1)
   - File Explorer windows (each counts as 1)
   - Right-click multiple folders → Open with Notepad
   - Open multiple browser tabs (each tab = 1 process)
3. Watch the "Processes Captured" counter increase
4. When it reaches 50+, click "⏹ Stop Recording"
5. CSV will be saved to data/ folder
```

### Option 2: Natural Recording (1-2 days)
```
1. Click "▶ Start Recording"  in the morning
2. Use your computer normally throughout the day
3. Every time you open an app, it gets recorded
4. At end of day, click "⏹ Stop Recording"
5. If you launched 50+ apps, CSV will be saved
```

---

## Testing Right Now

### Test Script to Verify Recording Works

Run this while the app is open with "Start Recording" active:

```powershell
# Open 10 test applications
1..10 | ForEach-Object {
    Start-Process notepad
    Start-Sleep -Milliseconds 500
}
```

Watch the "Processes Captured" counter increase from 0 to 10.

Then click Stop Recording and check the data/ folder for a new CSV file.

---

## Still Not Working?

If the counter stays at 0 even after opening apps:

### Check 1: Are you running from source or .exe?
- **Source** (`python main.py`): Should work
- **.exe** (`dist\KeyloggerDetector.exe`): Needs to be rebuilt with latest code

### Check 2: Check the logs
```powershell
Get-Content logs\detector.log -Tail 50
```

Look for errors related to "Recording" or "BehaviorRecordingStore".

### Check 3: Database permissions
The app needs write access to `logs\keylogger_events.db`.

---

## What Gets Saved

When recording works, you'll see a file like:
```
data/my_behavior_20261007_153045.csv
```

This contains:
- Process names (chrome.exe, notepad.exe, etc.)
- PIDs
- 24 behavioral features per process
- All labeled as "safe" (your normal usage)

This CSV is used to train the ML model to recognize your normal behavior patterns.

---

## Summary

**Recording is NOT automatic**. You must:
1. Click Start Recording
2. **Actively launch 50+ new applications**
3. Click Stop Recording

If you just let the computer sit idle, counter stays at 0 and nothing saves.

The counter in your screenshot shows "Processes Captured: 0" → This means no new apps were launched during that recording session.
