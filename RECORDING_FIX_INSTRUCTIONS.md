# Recording CSV Export - Diagnosis & Fix

## What I Changed

Added detailed logging to help diagnose why CSV files aren't being saved:

### Changes Made:
1. **Enhanced `_on_stop_recording()` in dashboard.py**
   - Logs the process count and duration before stopping
   - Logs what `recorder.stop()` returns
   - Shows more helpful error message with actual counts

2. **Enhanced `RecordingManager.stop()` in dashboard.py**
   - Logs session_id and count when stop is called
   - Logs the CSV export path before attempting export
   - Logs success with row count
   - Logs full error trace if export fails

---

## Next Steps

### Option 1: Test with Source Code (RECOMMENDED)

Run from source to see the detailed logs:

```powershell
# Make sure the app isn't already running
python main.py
```

Then:
1. Go to "Train Personalized Model" tab
2. Click "▶ Start Recording"
3. **Open at least 5 new applications** (Chrome, Notepad, Calculator, File Explorer, etc.)
4. Verify the "Processes Captured" counter shows a number > 0
5. Click "⏹ Stop Recording"
6. Check `logs\detector.log` for the new log messages

### Option 2: Rebuild the .exe

If you want to test with the executable:

```powershell
.\build.ps1 -Clean
```

Then run `dist\KeyloggerDetector.exe` and repeat the test.

---

## What the Logs Will Tell Us

After you click "Stop Recording", check `logs\detector.log`:

### If count was 0:
```
Stop Recording clicked: count=0, elapsed=120.0s
No CSV export: count=0, session_id=abc123...
```
**Diagnosis**: No apps were launched → No CSV saved (correct behavior)

### If count was > 0 but CSV failed:
```
Stop Recording clicked: count=25, elapsed=300.0s
RecordingManager.stop() called: session_id=abc123, count=25
Attempting CSV export to: C:\...\data\my_behavior_20261007_153045.csv
CSV export failed: <error message>
```
**Diagnosis**: Real bug - processes were recorded but export failed

### If count was > 0 and CSV succeeded:
```
Stop Recording clicked: count=56, elapsed=400.0s
RecordingManager.stop() called: session_id=abc123, count=56
Attempting CSV export to: C:\...\data\my_behavior_20261007_153045.csv
CSV export successful: 56 rows written to C:\...\data\my_behavior_20261007_153045.csv
```
**Diagnosis**: Everything working correctly

---

## Testing Instructions

### Quick Test (5 minutes):

```powershell
# 1. Start the app from source
python main.py

# 2. In another PowerShell window, run this to launch 10 test processes:
1..10 | ForEach-Object {
    Start-Process notepad
    Start-Sleep -Milliseconds 500
}

# 3. In the app:
#    - Go to "Train Personalized Model" tab
#    - Click "▶ Start Recording"
#    - Run the above PowerShell command
#    - Watch counter go from 0 to 10
#    - Click "⏹ Stop Recording"

# 4. Check the logs:
Get-Content logs\detector.log -Tail 20
```

---

## Expected Behavior

### Recording Flow:
```
User clicks Start
  ↓
App takes baseline snapshot of all running PIDs
  ↓
Background thread polls for new processes every 3 seconds
  ↓
User launches new apps (Chrome, Notepad, etc.)
  ↓
Each new PID gets features extracted and saved to database
  ↓
Counter increases in UI
  ↓
User clicks Stop
  ↓
Thread stops polling
  ↓
If count > 0: Export session to CSV
  ↓
CSV appears in data/ folder
```

### What Gets Recorded:
- ✅ Applications launched AFTER clicking Start
- ❌ Applications already running when Start was clicked
- ❌ System processes (filtered out)
- ❌ Typing/mouse data (different feature, different tab)

---

## Common Issues

### Issue 1: Counter stays at 0
**Cause**: No new applications were launched, or only system processes were launched
**Solution**: Manually open user applications like Chrome, Notepad, Calculator

### Issue 2: Counter increases but CSV doesn't save
**Cause**: Could be permission issue, pandas import error, or database lock
**Solution**: Check the logs for the exact error message

### Issue 3: CSV saves but file is empty
**Cause**: Database write failed or feature extraction failed
**Solution**: Check if `behavior_recordings` table has data:
```powershell
python check_recording_table.py
```

---

## Manual Export

If you have data in the database but no CSV, you can manually export:

```powershell
python manual_export_csv.py
```

This will export all sessions to CSV files in the data/ folder.

---

## Questions to Answer

After testing, please tell me:

1. **What did the "Processes Captured" counter show when you clicked Stop?**
   - Was it 0?
   - Or was it > 0 (like 10, 25, 50)?

2. **What message appeared when you clicked Stop?**
   - "No Data Recorded"?
   - "Too Few Samples"?
   - "Recording Complete"?
   - Or nothing?

3. **What do the logs say?**
   ```powershell
   Get-Content logs\detector.log -Tail 30
   ```

With this information, I can pinpoint the exact issue!
