# 🔧 How to Rebuild the .exe with New Changes

## ❌ Problem

The .exe file you're running was built with the **old code** before we changed the thresholds. You need to rebuild it to include the new changes:

**Changes made:**
- ✅ Keystroke requirement: 10,000 → 2,000
- ✅ Mouse requirement: 15,000 → 3,000  
- ✅ Minimum keystrokes per cycle: 20 → 5
- ✅ Minimum mouse per cycle: 15 → 5

---

## ✅ Solution: Rebuild the .exe

### **Step 1: Close ALL Running Instances**

**IMPORTANT:** The .exe file cannot be replaced while it's running!

1. Close the KeyloggerDetector application (if open)
2. Check system tray and close it there too (right-click → Quit)
3. Open Task Manager (Ctrl+Shift+Esc)
4. Look for these processes and **End Task**:
   - `KeyloggerDetector.exe`
   - `python.exe` (any related to Keylogger project)

**OR use PowerShell:**
```powershell
Get-Process | Where-Object { $_.Name -like "*KeyloggerDetector*" } | Stop-Process -Force
```

---

### **Step 2: Rebuild the Executable**

Open PowerShell in the project folder and run:

```powershell
cd C:\Users\Anto\OneDrive\Desktop\Keylogger
python -m PyInstaller keylogger_detector.spec --noconfirm
```

**Wait for it to complete (~2-3 minutes)**

Look for this at the end:
```
INFO: Building EXE from EXE-00.toc completed successfully.
```

---

### **Step 3: Verify the New .exe**

Check the file timestamp:

```powershell
Get-Item .\dist\KeyloggerDetector.exe | Select-Object Name, LastWriteTime, @{Name="Size (MB)";Expression={[math]::Round($_.Length/1MB, 2)}}
```

**Expected:**
- LastWriteTime: Should be current date/time (today)
- Size: ~75-80 MB

---

### **Step 4: Test the New .exe**

1. **Run the new executable:**
   ```
   .\dist\KeyloggerDetector.exe
   ```
   or double-click the desktop shortcut

2. **Go to Behavioral Analysis tab**

3. **Check the requirements:**
   ```
   Training Progress:
   Keystrokes: 0 / 2,000 (0%)    ← Should show 2,000 (not 10,000)
   Mouse: 0 / 3,000 (0%)           ← Should show 3,000 (not 15,000)
   ```

4. **Type and move mouse**

5. **Verify data is being collected:**
   ```powershell
   python check_training_data.py
   ```

---

## 🎯 Alternative: Run from Source (No Rebuild Needed!)

If rebuilding is problematic, you can run directly from Python source with the new changes:

```bash
python main.py
```

**Advantages:**
- ✅ Uses latest code immediately (no rebuild needed)
- ✅ Faster to test changes
- ✅ Easier to debug

**Disadvantages:**
- ⚠️ Requires Python to be installed
- ⚠️ Shows console window
- ⚠️ Can't double-click from desktop

---

## 📝 Quick Reference

### **Full Rebuild Process (One Command)**

```powershell
# Navigate to project
cd C:\Users\Anto\OneDrive\Desktop\Keylogger

# Stop any running instances
Get-Process | Where-Object { $_.Name -eq "KeyloggerDetector" } | Stop-Process -Force

# Wait 2 seconds
Start-Sleep -Seconds 2

# Rebuild
python -m PyInstaller keylogger_detector.spec --noconfirm

# Check result
Get-Item .\dist\KeyloggerDetector.exe | Select-Object LastWriteTime
```

---

## ❓ Troubleshooting

### **"PermissionError: Access is denied"**

**Cause:** .exe is still running

**Solution:**
1. Close the app completely
2. Check Task Manager for `KeyloggerDetector.exe`
3. End all instances
4. Try rebuild again

---

### **Build Takes Too Long**

**Expected time:** 2-5 minutes

If longer than 10 minutes:
- Press Ctrl+C to cancel
- Check if antivirus is scanning (pause it temporarily)
- Try again

---

### **"PyInstaller not found"**

```bash
pip install pyinstaller
```

---

### **Changes Still Not Applied**

1. Verify you're running the NEW .exe:
   ```powershell
   Get-Item .\dist\KeyloggerDetector.exe | Select-Object LastWriteTime
   ```
   Should show today's date

2. Or delete old .exe and rebuild:
   ```powershell
   Remove-Item .\dist\KeyloggerDetector.exe -Force
   python -m PyInstaller keylogger_detector.spec --noconfirm
   ```

---

## ✅ Summary

**To apply changes to the .exe:**

1. **Close all instances** of KeyloggerDetector
2. **Rebuild:** `python -m PyInstaller keylogger_detector.spec --noconfirm`
3. **Test:** Run new .exe and check it shows 2,000/3,000 (not 10,000/15,000)

**OR just run from source:**
```bash
python main.py
```

---

**Current Status:**
- ✅ Source code updated with new thresholds (2,000 keystrokes, 3,000 mouse)
- ⏳ .exe needs to be rebuilt to include these changes
- ✅ Running `python main.py` will use the new code immediately
