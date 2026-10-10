# Demo Day Reset Guide

## Two-Tier Baseline System (NEW)

The app now uses a **two-tier baseline collection strategy** for optimal demo experience:

### Tier 1: UI Unlock (Fast Demo Start)
- **Threshold:** 120 keystrokes + 200 mouse movements
- **Time:** ~90 seconds of normal computer use
- **Effect:** App unlocks, monitoring enabled, progress banner removed
- **Purpose:** Fast first-impression for judges

### Tier 2: Full Baseline (Silent Background)
- **Threshold:** 2000 keystrokes + 3000 mouse movements  
- **Collection:** Continues silently in background after UI unlock
- **Updates:** Baseline statistics refresh incrementally (every 100 ks / 200 mouse)
- **Purpose:** Full statistical confidence for production-grade detection

## Clean Environment Reset (Before Demo)

Your test machine retains behavioral data from previous testing sessions. To show judges a **fresh, first-run experience**, reset your environment:

### Step 1: Delete User Data Folder

Run this PowerShell command to wipe all behavioral history:

```powershell
Remove-Item "$env:LOCALAPPDATA\KeyloggerDetector" -Recurse -Force
```

This deletes:
- ✅ Baseline profiles (`typing_baseline.json`, `mouse_baseline.json`)
- ✅ Training progress (`baseline_progress.json`)
- ✅ Event history database (`keylogger_events.db`)
- ✅ All behavioral exports

### Step 2: Launch the App

After reset, the app will:
1. Show **empty training progress** (0/120 ks, 0/200 mouse)
2. Collect baseline from scratch
3. Unlock monitoring at 120/200 (~90 seconds)
4. Continue silent collection to 2000/3000 in background

## When to Reset

### ✅ DO Reset Before:
- **Final rehearsal** (if you want to practice the full first-run flow)
- **Actual demo presentation** (judges see a clean first impression)

### ❌ DON'T Reset If:
- Still developing/testing features (you'll lose your real baseline)
- Want to show established behavioral monitoring (not first-run flow)

## Demo Day Recommendation

**Best practice:**
1. Test all features with your current baseline (don't reset yet)
2. **1 hour before demo:** Run the reset command
3. Launch app naturally during demo intro (shows 0/120 training UI)
4. While explaining the system, type/mouse normally to demonstrate live collection
5. By the time you finish explaining, baseline will unlock (~90 seconds)
6. Show live monitoring with fresh, clean slate

## Production Behavior (No Reset)

If judges ask **"What happens if I reinstall?"**:

**Correct answer:** 
> "The installer only affects the program files in `C:\Program Files\KeyloggerDetector\`. Your personal baseline, progress, and history live in `%LOCALAPPDATA%\KeyloggerDetector\` (per-user data folder), which is deliberately preserved across reinstalls. This is standard practice — you don't lose your settings when you reinstall Chrome or VS Code. If you truly want to start fresh, you'd manually delete that data folder."

## Minimum Requirements

- **UI Unlock:** 120 keystrokes + 200 mouse movements (~90 seconds)
- **Full Baseline:** 2000 keystrokes + 3000 mouse movements (continues silently)
- **Environment Override:** Set `KGAI_BASELINE_KEYSTROKES` and `KGAI_BASELINE_MOUSE` to customize (not recommended for demos)

## What Judges Will See

### Before Reset (Your Test Machine)
- "✅ Complete — Baseline Saved!" (already trained)
- Monitoring view active immediately
- Full history from tonight's testing

### After Reset (Fresh Start)
- "Learning Your Natural Behavior Profile" (training UI visible)
- Progress bar at 0.0%
- Live collection countdown (120/200 → unlock)
- Clean history, no previous alerts

Choose the experience that best demonstrates your system's capabilities!
