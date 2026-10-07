# 🔧 Troubleshooting: Baseline Not Saving After 2 Hours

## 🚨 Problem Identified

After 2 hours of training, you only have:
- **3 typing records** (need 2,000) - only 0.15% complete!
- **43 mouse records** (need 3,000) - only 1.4% complete!

**This is WAY too low!** At this rate, it would take **~2,778 hours (115 days)** to complete!

---

## 🔍 Root Cause

The behavioral analyzer is **NOT collecting data properly**. Here's why:

### **How Data Collection Works:**

1. **Analysis cycles run every 60 seconds**
2. **Minimum thresholds per cycle:**
   - At least **20 keystrokes** in 60 seconds to log typing data
   - At least **15 mouse movements** in 60 seconds to log mouse data
3. **If thresholds not met:** No data is saved!

### **Your Situation:**

```
After 2 hours (120 minutes):
- 120 minutes ÷ 1 minute cycles = 120 possible cycles
- Only 3 typing records saved = 3 cycles with 20+ keystrokes
- Only 43 mouse records saved = 43 cycles with 15+ mouse movements

This means:
- 97.5% of cycles had < 20 keystrokes (data discarded!)
- 64% of cycles had < 15 mouse movements (data discarded!)
```

---

## ❓ Why Is This Happening?

### **Possible Causes:**

#### **1. Application is Running in Background**
If the Behavioral Analysis tab is not open:
- The UI might not be triggering updates
- Recording might be paused

#### **2. Minimal Computer Usage**
If you're mostly:
- Watching videos
- Reading (no typing)
- Using mouse sparingly
- Working in apps that don't generate keyboard events

**Result:** Not enough activity per 60-second window

#### **3. pynput Not Capturing Events**
- Some applications block keyboard hooks
- Remote desktop sessions
- Virtual machines
- Certain games/fullscreen apps

#### **4. Recording Not Active**
- Behavioral Analysis tab never opened
- Engine started but listeners failed
- Permission issues

---

## ✅ Solutions

### **Solution 1: Keep Behavioral Analysis Tab Open** ⭐ RECOMMENDED

**The tab MUST be open for data collection to work properly!**

1. Run the application
2. **Click on "Behavioral Analysis" tab**
3. **Leave it open** while you use your computer
4. The tab shows real-time progress

**Why:** The UI refresh triggers data processing cycles.

---

### **Solution 2: Use Computer More Actively**

To meet the **20 keystrokes per minute** threshold:

**Good Activities:**
- ✅ **Typing emails** (high keystroke rate)
- ✅ **Coding/programming** (continuous typing)
- ✅ **Writing documents** (Word, Notepad++)
- ✅ **Chatting** (Slack, Teams, WhatsApp)
- ✅ **Web browsing** (typing URLs, searches)
- ✅ **Terminal commands** (if you're a developer)

**Poor Activities:**
- ❌ Watching videos (no keystrokes)
- ❌ Reading PDFs (no keystrokes)
- ❌ Scrolling social media (minimal typing)
- ❌ Gaming (game hooks might block pynput)

**Tip:** Type at least **one character every 3 seconds** during active use.

---

### **Solution 3: Lower the Minimum Thresholds (Temporary)**

If you have light computer usage patterns, temporarily lower thresholds:

**Edit:** `src/behavioral_analyzer.py` (line 60-61)

```python
# Current (strict):
MIN_KS_FOR_ANALYSIS     = 20             # minimum keystrokes needed to analyse
MIN_MOUSE_FOR_ANALYSIS  = 15             # minimum mouse movements to analyse

# Change to (lenient):
MIN_KS_FOR_ANALYSIS     = 5              # minimum keystrokes needed to analyse
MIN_MOUSE_FOR_ANALYSIS  = 5              # minimum mouse movements to analyse
```

**This will:**
- ✅ Capture more cycles (even with light usage)
- ✅ Speed up data collection significantly
- ⚠️ Slightly reduce data quality (more noise)

**Restore to 20/15 after collecting baseline.**

---

### **Solution 4: Manual Data Collection Session**

Dedicate 30-60 minutes of focused typing to speed things up:

```
Task: Write a 500-word document or email
Time: 30 minutes
Expected: ~2,000 keystrokes in one session!

Result: Training complete in 1 session! ✅
```

**Example tasks:**
- Write a long email
- Document something
- Code a small project
- Transcribe text
- Write in a journal

---

### **Solution 5: Verify Recording is Active**

Run this diagnostic:

```bash
python check_training_data.py
```

**Expected output if working:**
```
✅ Typing behavior records: [increasing number]
✅ Mouse behavior records: [increasing number]
```

**If you see "0 records":**
- Behavioral Analysis tab not opened
- Recording failed to start
- pynput not working

---

### **Solution 6: Force Recording Restart**

1. Close the application completely
2. Check Task Manager - ensure no `python.exe` processes remain
3. Delete old database (backup first):
   ```powershell
   Rename-Item logs\keylogger_events.db logs\keylogger_events.db.backup
   ```
4. Restart application
5. **Open Behavioral Analysis tab immediately**
6. Start typing and moving mouse
7. Wait 2 minutes
8. Run `python check_training_data.py` to verify data is being collected

---

## 📊 How to Monitor Progress

### **Real-Time Progress (in the app):**

Open **Behavioral Analysis tab** and watch:

```
Training Progress:
Keystrokes: 245 / 2,000 (12.3%)  ← Should increase every minute if typing
Mouse Movements: 567 / 3,000 (18.9%)  ← Should increase constantly

Current Speeds:
65 WPM | 450 px/s  ← Shows you're actively using computer
```

### **Check Database (command line):**

```bash
python check_training_data.py
```

Run this every 5-10 minutes to verify data is accumulating.

---

## ⏱️ Realistic Timeline With Active Usage

### **Scenario 1: Focused Typing Session**
```
Activity: Continuous typing (emails, coding, writing)
Rate: ~60 WPM = ~300 characters/minute = ~300 keystrokes/minute
Time to 2,000 keystrokes: ~7 minutes of pure typing ✅

Mouse: Moderate usage
Rate: ~100 movements/minute
Time to 3,000 movements: ~30 minutes ✅

Total: ~30-60 minutes of active work
```

### **Scenario 2: Normal Computer Use**
```
Activity: Mixed usage (browsing, emails, some typing)
Rate: ~20 keystrokes/minute average (including pauses)
Time to 2,000 keystrokes: ~100 minutes = 1.7 hours ✅

Mouse: Normal usage
Rate: ~50 movements/minute
Time to 3,000 movements: ~60 minutes = 1 hour ✅

Total: ~2-4 hours spread across 1-2 days
```

### **Scenario 3: Light Usage (Your Current Situation)**
```
Activity: Mostly watching, reading, minimal typing
Rate: ~2 keystrokes/minute (below minimum threshold!)
Time to 2,000 keystrokes: NEVER (data not logged) ❌

Problem: Not meeting 20 keystrokes/minute minimum
Solution: Use Solution 3 (lower thresholds) or Solution 4 (focused session)
```

---

## 🎯 Recommended Action Plan

### **Immediate Actions:**

1. **✅ Step 1:** Lower the thresholds (Solution 3)
   ```python
   MIN_KS_FOR_ANALYSIS = 5
   MIN_MOUSE_FOR_ANALYSIS = 5
   ```

2. **✅ Step 2:** Restart the application

3. **✅ Step 3:** Open Behavioral Analysis tab and KEEP IT OPEN

4. **✅ Step 4:** Do a 30-minute focused typing session (write something)

5. **✅ Step 5:** Verify progress with `python check_training_data.py`

6. **✅ Step 6:** Continue normal usage with tab open

7. **✅ Step 7:** Once complete, restore thresholds to 20/15

---

## 📝 Quick Diagnostic Checklist

Run through this checklist:

- [ ] Is the application running?
- [ ] Is the **Behavioral Analysis tab open**?
- [ ] Does the progress show increasing numbers?
- [ ] Are you typing at least **20 characters per minute**?
- [ ] Are you moving the mouse regularly?
- [ ] Does `check_training_data.py` show increasing records?
- [ ] Is pynput installed? (`python -c "import pynput"`)
- [ ] Are you using a regular desktop/laptop (not remote desktop)?

---

## 🔥 Fast Track Solution (Get Baseline in 1 Hour)

**If you just want to complete training quickly:**

1. **Lower thresholds:**
   ```python
   MIN_KS_FOR_ANALYSIS = 5
   MIN_MOUSE_FOR_ANALYSIS = 5
   ```

2. **Start app with Behavioral Analysis tab open**

3. **Type continuously for 30 minutes:**
   - Write emails
   - Code something
   - Document your project
   - Chat with someone
   - Type your thoughts

4. **Move mouse frequently while typing**

5. **Check progress every 10 minutes**

6. **Training should complete in ~1 hour**

---

## 📞 Still Not Working?

If data is still not being collected:

### **Check the logs:**
```bash
Get-Content logs\detector.log -Tail 100 | Select-String "behavioral"
```

Look for:
- ✅ "BehavioralAnalysisEngine started"
- ✅ "KeystrokeRecorder started"
- ✅ "MouseRecorder started"
- ❌ Any error messages

### **Verify pynput works:**
```python
python -c "from pynput import keyboard, mouse; print('pynput OK')"
```

### **Test keyboard recording:**
```python
from pynput import keyboard

def on_press(key):
    print(f'Key pressed: {key}')

listener = keyboard.Listener(on_press=on_press)
listener.start()

input('Type some keys, then press Enter to stop...')
listener.stop()
```

---

## ✅ Success Indicators

You'll know it's working when:

1. **✅ Behavioral Analysis tab shows increasing numbers every minute**
2. **✅ `check_training_data.py` shows hundreds/thousands of records**
3. **✅ Progress percentage increases visibly**
4. **✅ After reaching 100%, you see:**
   - Green completion banner
   - Desktop notification
   - Files appear in `data/` folder:
     - `typing_baseline.json`
     - `mouse_baseline.json`
     - `keyboard_behavior.json`
     - `mouse_behavior.json`
     - `behavioral_profile.json`

---

## 📚 Summary

**Your issue:** Only 3 typing records in 2 hours (should be ~2,000+)

**Root cause:** Not meeting 20 keystrokes/minute threshold consistently

**Best solution:** 
1. Lower thresholds to 5 keystrokes/minute (temporary)
2. Keep Behavioral Analysis tab open
3. Do focused typing session
4. Complete training in 1-2 hours!

**Expected result:** Baseline saved automatically when thresholds reached!

---

Would you like me to apply Solution 3 (lower the thresholds) for you right now?
