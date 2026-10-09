# Known Limitations

This document provides honest disclosure of known limitations in the AI-Based Keylogger Detection System. These are design tradeoffs, implementation constraints, and areas where the current system does not meet ideal performance or robustness standards.

---

## 1. Zero-Hook Polling-Based Capture

The system uses user-space polling (GetAsyncKeyState, GetCursorPos) rather than OS-level keyboard/mouse hooks. This approach is less invasive and carries lower system risk than kernel-level hooking, but it is theoretically less robust against highly sophisticated evasion techniques. An attacker with deep system knowledge could potentially craft input injection methods that bypass user-space polling, though such techniques would require significantly more effort than evading standard application-layer hooks.

---

## 2. Keystroke Polling Under Thread Contention

Keystroke polling can occasionally miss keystrokes under heavy system thread contention. This has been observed and measured during testing, with polling cycle times ranging from the ~4ms target up to 1500ms+ under high CPU load. Mitigations have been applied (reduced scan key-range from 247 to ~60 keys, elevated thread priority to TIME_CRITICAL, Windows high-resolution timer activation), but the issue is not fully eliminated. This does NOT corrupt any already-collected data — it only means baseline training may take longer in real-world use than the raw target sample counts suggest. A hybrid hook-assisted capture layer is potential future work.

---

## 3. ML Accuracy and Detection Confidence

ML accuracy percentages, bot-detection confidence levels, and false-positive-reduction claims referenced in the project's documentation are design targets based on internal thresholds and heuristics, not validated against a labeled real-world test dataset.

---

## 4. Baseline Training Data Volume

Production defaults require a meaningful volume of real typing and mouse activity (2,000 keystrokes and 3,000 mouse movements) to build a statistically meaningful behavioral baseline. This naturally takes time in real-world use. A reduced-threshold "demo mode" exists via environment variables (`KGAI_BASELINE_KEYSTROKES` and `KGAI_BASELINE_MOUSE`) for demonstration purposes only. Demo mode allows baseline completion in 1-2 minutes but is explicitly not representative of real-world baseline quality or detection accuracy.

---

## 5. Administrator Elevation and Code Signing

The application currently always requires administrator elevation to run. It is distributed as an unsigned executable, meaning Windows SmartScreen or Windows Defender may show a warning on first run. No code-signing certificate has been obtained for this submission.

---

## 6. No Autostart-on-Boot

No autostart-on-boot functionality is currently implemented. The application must be launched manually each session after system restart. This is a deliberate design choice for the current submission to avoid persistent installation complexity, but it means protection is not continuous across reboots unless the user explicitly relaunches the application.

---

## 7. Platform Support

The application is Windows-only. There is no Linux or macOS support, and none is currently planned.

---

## 8. No Centralized or Cloud Logging

All detection, alerts, and behavioral data are stored and processed entirely locally on the device. There is no remote monitoring, centralized dashboard, or cloud sync.

---

## 9. Local Database Storage

Data is stored in a local SQLite database, which is suitable for a single-user desktop tool but is not an enterprise-grade or multi-client database system.

---

## 10. Detection Latency

Behavioral analysis runs on a fixed 60-second cycle (`src/behavioral_analyzer.py`, `ANALYSIS_WINDOW_SECS`), meaning behavioral anomaly detection is not instantaneous — there can be up to approximately 60 seconds of latency between an event occurring and it being analyzed. Process-based malicious software detection runs on a separate, faster scan interval and is not affected by this.

---

## 11. Manual Whitelist Management

Whitelist management is entirely manual. A user must explicitly whitelist a process via the dashboard UI. There is no automatic learning or trust-building for repeatedly-seen safe processes.

---

## 12. No Automatic Update Mechanism

The application does not currently check for or download updates to its ML model, detection logic, or software version. Updates must be installed manually.

---

## 13. Single-User Design

The application is designed for a single-user Windows workstation. It has not been designed or tested for multi-user or shared/server environments.

---

## 14. Keyboard Layout and Language

Behavioral (keystroke dynamics) analysis has not been validated on non-QWERTY keyboard layouts or non-English typing patterns. Accuracy on such configurations is unknown.

---

## Summary

These limitations are documented transparently as part of the project's honest assessment of its current state. Many of them represent conscious design tradeoffs (e.g., polling vs. hooking, no autostart), while others (e.g., thread contention, lack of external validation) are areas for potential future improvement. The system is functional and demonstrates the core behavioral biometrics and anomaly detection approach, but it is not production-hardened for enterprise deployment without addressing these constraints.
