# Multi-Modal Behavioral Biometrics Guide
## Phase 1 & Phase 2 — Keyboard & Mouse Dynamics Anomaly Detection

---

## 1. Overview

KeyGuard AI incorporates a **Multi-Modal Behavioral Biometrics System** that continuously and passively monitors your system interactions (keyboard timing dynamics and mouse trajectory physics) to detect:
* **Unauthorized Users / Impersonation**: Detects when someone else is using your workstation (accuracy increases from 70–80% with keyboard alone to **90–95%** with combined keyboard + mouse).
* **Automated Scripts & Bots**: Differentiates between macros, remote control screen sharing sessions, replay attacks, and hybrid automation.
* **Keylogger Replay Attacks**: Identifies exact playback of intercepted timing sequences.

---

## 2. Privacy Guarantee

> **KeyGuard AI never records screen pixels, screenshots, or typed text.**

* **Keyboard**: Only timing intervals (dwell hold times, flight gaps) and irreversible hash identifiers are analyzed.
* **Mouse**: Only movement speeds ($px/s$), acceleration ($px/s^2$), path curvature, jitter/tremor, click hold durations, and aggregate zone heatmaps are processed.
* **Exports**: All JSON exports contain SHA-256 integrity hashes and can anonymize timestamps into relative time offsets ($T+0\text{s}$).

---

## 3. Metrics Tracked

### A. Keyboard Biometrics
* **Typing Speed (WPM)**: Words per minute ($5\text{ chars} = 1\text{ word}$).
* **Dwell Time**: Key hold duration ($\text{ms}$).
* **Flight Time**: Inter-key interval ($\text{ms}$).
* **Consistency**: Standard deviation of key intervals ($\text{ms}$).
* **Burst Dynamics**: Number of continuous typing bursts and average burst duration.

### B. Mouse Biometrics
* **Movement Speed**: Pixels per second ($\text{px/s}$).
* **Path Curvature Index**: Ratio of actual path length to straight-line distance (Humans: 1.15–1.35; Bots: 1.00–1.05).
* **Micro-Movements / Tremor**: Sub-pixel hand tremor and trajectory direction changes per second (Humans: 6–12/s, 2–3px jitter; Bots: 0–1/s, 0px jitter).
* **Click Duration**: Button hold time ($\text{ms}$).
* **Double-Click Timing**: Interval between consecutive clicks $< 500\text{ ms}$.
* **Click-to-Move Latency**: Reaction time between releasing a click and initiating cursor movement (Humans: 300–800ms; Bots: $< 100\text{ms}$).
* **Movement Pause Frequency**: Frequency of pauses $> 1.0\text{s}$ per minute (Humans: 12–18/min; Bots: 0–2/min).
* **Screen Zone Distribution**: 3x3 quadrant grid heatmap distribution of cursor activity.

### C. Combined Pattern Correlation
* **Weighted Similarity Score**:
  $$\text{Overall Similarity} = (0.40 \times \text{KB Score}) + (0.40 \times \text{Mouse Score}) + (0.20 \times \text{Pattern Score})$$
* **Input Coordination**: Correlation between typing bursts and mouse movement pauses.
* **Switch Latency**: Hand transition time between keyboard and mouse.

---

## 4. Multi-Modal Bot Classification

KeyGuard AI detects four distinct bot architectures:

| Bot Type | Signature & Indicators | Trigger Condition |
| :--- | :--- | :--- |
| **Keyboard Macro** (`keyboard_macro`) | Mechanically uniform keystrokes without human mouse movement. | Keystroke std-dev $< 5\text{ ms}$ & mouse events $< 100$. |
| **Remote Control** (`remote_control`) | Straight geometric cursor paths with zero hand tremor. | Path curvature $< 1.05$ & jitter $< 1.0\text{ px}$. |
| **Replay Attack** (`replay_attack`) | Keystroke or mouse timing sequence exactly identical to previously logged intervals. | Exact timing sequence repetition without variance. |
| **Hybrid Automation** (`hybrid_automation`) | Asynchronous, uncoordinated input streams. | Activity correlation $< 0.30$ & unnatural switch latency. |

---

## 5. JSON Export & Backup

All profile and session data can be exported directly from the **Behavior** tab in the GUI:
* `keyboard_behavior.json`: Baseline keyboard profile.
* `mouse_behavior.json`: Baseline mouse profile.
* `behavioral_profile.json`: Combined multi-modal baseline.
* `session_[timestamp].json`: Rolling forensic session logs.
* `comparison_report.json`: Side-by-side metric comparison vs baseline.
