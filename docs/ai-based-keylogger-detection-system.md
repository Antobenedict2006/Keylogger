# AI-Based Keylogger Detection System

A lightweight Windows tool that watches running processes in real time to spot keylogger-like behavior, even from unknown malware. It scans other processes for keyboard-hook API usage (a detection signal for suspicious software) while using zero-hook polling-based capture (GetAsyncKeyState, GetCursorPos) for its own behavioral biometrics collection. It uses behavioral and heuristic analysis plus a machine learning model to score processes as safe, suspicious, or malicious, then alerts the user with the reason and offers one-click actions like terminate, quarantine, or whitelist.

**Skills:** Python, Windows API (pywin32/ctypes), psutil process monitoring, scikit-learn (Random Forest/Gradient Boosting), Feature engineering, SQLite, Tkinter or plyer for desktop UI/notifications, Malware sandboxing and VM-based testing, Data logging and log analysis

---

## Overview
This project builds a lightweight, AI-powered application for Windows that detects keylogger-style malware in real time by watching how processes behave rather than matching them against known malware signatures. It runs continuously in the background, flags suspicious processes with an explanation, and lets the user immediately terminate, quarantine, or whitelist them.

## Problem
Keyloggers silently capture keystrokes to steal passwords, banking details, and personal data. Traditional antivirus tools rely on signature databases and routinely miss new, modified, or fileless keyloggers. Home users, freelancers, students, and small businesses often lack the budget or expertise for enterprise-grade Endpoint Detection and Response (EDR) platforms, leaving a gap between "no protection" and expensive security stacks.

## Proposed Solution
The system monitors running processes and Windows input-related APIs to build a behavioral profile for each process, then uses a machine learning classifier to assign a suspicion score. When a process crosses a threshold, the system alerts the user with the specific indicators that triggered the flag and offers immediate response options. All flagged events are logged locally for review and to improve future detection.

## Key Features
- Real-time monitoring of processes to detect OTHER processes using low-level keyboard hooks (e.g., `WH_KEYBOARD_LL`, raw input APIs) as a threat indicator
- Behavioral feature extraction: hook detection frequency in scanned processes, hidden/no-UI processes, unusual file writes, suspicious network activity following keystroke capture
- ML-based classification (Random Forest/Gradient Boosting) producing Safe/Suspicious/Malicious risk levels
- Desktop alerts showing process name, PID, and the exact behavioral reasons for flagging
- One-click response: terminate, quarantine (suspend + isolate), or whitelist (feeds back into future tuning)
- Local SQLite event log for audit and review

## Technical Approach
The core is written in Python for rapid iteration and access to both system and ML libraries. `psutil` handles process enumeration and resource stats, while `pywin32`/`ctypes` provide access to Windows APIs for detecting hook usage in OTHER processes (not for this app's own input capture). This application's own behavioral biometric data capture uses polling-based methods (GetAsyncKeyState at 250Hz for keyboard timing, GetCursorPos at 20Hz for mouse tracking) rather than OS-level hooks like SetWindowsHookEx. This is a deliberate engineering tradeoff: polling-based capture reduces performance overhead and crash risk compared to OS-level hook injection, at the cost of not using Windows' native injected-input flags (e.g. LLKHF_INJECTED) as a detection signal. Adding hook-based verification as a second detection layer is a planned future improvement. Raw monitoring data is converted into structured feature vectors (hook type/frequency detected in other processes, file I/O patterns, process metadata such as unsigned binaries or startup persistence, and network call patterns) using `pandas`/`numpy`. These features feed a `scikit-learn` classifier trained on labeled traces of known keyloggers versus legitimate applications (browsers, IDEs, chat apps, games) to keep false positives low on input-heavy but benign software. Alerts are surfaced via a lightweight system-tray app or minimal Tkinter dashboard using `plyer` for notifications, and all events are stored in SQLite for logging and later retraining.

## Architecture
The pipeline flows in four stages: (1) a Process & Keyboard-Hook Monitoring Module continuously scans the OS for hook API registrations in OTHER processes, file writes, and network calls; (2) a Feature Extraction Engine converts raw events into per-process behavioral profiles updated every 5-10 seconds; (3) the AI Classification Model scores each profile and assigns a risk level; (4) the Alert & Response Module surfaces notifications and executes user-chosen actions, while logging everything to SQLite for audit and future model improvement.

## Milestones
1. Build the process enumeration and keyboard-hook detection module (for detecting hook API usage in other processes), logging raw events to structured files.
2. Implement feature extraction from raw logs and assemble a labeled dataset of keylogger vs. benign application behavior.
3. Train and evaluate a baseline classifier (Random Forest/Gradient Boosting) and integrate it into a near real-time scoring pipeline.
4. Build the alert and response module (notifications plus terminate/quarantine/whitelist actions) connected end-to-end to the detection pipeline.
5. Build the dashboard UI, test against sandboxed keylogger samples and common benign apps, and tune thresholds to reduce false positives.
6. Finalize documentation and prepare a demo showing the full monitor-to-response pipeline.

## Success Metrics
- Detection accuracy against a curated set of known keylogger samples run in an isolated VM
- False-positive rate on a set of common benign, input-heavy applications (games, accessibility tools, IDEs)
- End-to-end latency from suspicious behavior onset to user alert
- Background CPU/RAM footprint during continuous monitoring
- Successful completion of alert-to-action flow (terminate/quarantine/whitelist) in test scenarios
