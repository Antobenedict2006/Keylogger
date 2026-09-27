# JSON Behavioral Data Export Guide
## KeyGuard AI — Phase 2 Multi-Modal Biometrics Specification

---

## 1. Overview

KeyGuard AI provides comprehensive JSON export capabilities for all collected behavioral biometrics across keyboard dynamics, mouse trajectory patterns, session forensic logs, and comparative baseline reports.

### Export Capabilities
1. **Profile Baselines**:
   * `keyboard_behavior.json`: Baseline typing metrics, distributions, percentiles, time-of-day dynamics, and application context.
   * `mouse_behavior.json`: Baseline mouse speeds, curvature complexity, micro-movements/tremors, click hold times, double-click timings, and 3x3 screen spatial distribution.
   * `behavioral_profile.json`: Multi-modal unified profile.
2. **Session Forensics**:
   * `session_[timestamp].json`: Rolling 60-second window activity logs, deviations, $Z$-scores, and anomaly events.
3. **Comparative Analysis**:
   * `comparison_report.json`: Side-by-side comparison of baseline vs current session metrics with verdict and recommendations.

---

## 2. Privacy & Integrity Guarantees

* **Zero Content Recording**: Screen coordinates are excluded by default; keystrokes are represented only as duration and flight intervals; screen pixels and character keys are **never** recorded.
* **SHA-256 Verification**: Every exported JSON includes a `file_metadata` section containing a SHA-256 hash of the payload for integrity validation.
* **Timestamp Anonymization**: Session exports can be anonymized using relative time offsets ($T+0\text{s}$, $T+60\text{s}$, etc.).

---

## 3. JSON File Format Specifications

### A. Keyboard Profile (`data/keyboard_behavior.json`)

```json
{
  "export_metadata": {
    "export_timestamp": "2026-01-20T15:30:00Z",
    "software_version": "2.5.0",
    "data_type": "behavioral_baseline",
    "user_note": "Training completed after 2 weeks normal usage"
  },
  "keyboard_profile": {
    "training_period": {
      "start_date": "2026-01-01T09:00:00Z",
      "end_date": "2026-01-15T18:30:00Z",
      "total_duration_hours": 336.0,
      "total_keystrokes": 15234
    },
    "baseline_metrics": {
      "typing_speed": {
        "mean_wpm": 65,
        "stddev_wpm": 8,
        "min_wpm": 45,
        "max_wpm": 85,
        "percentile_25": 60,
        "percentile_50": 65,
        "percentile_75": 72,
        "percentile_95": 78
      },
      "dwell_time_ms": {
        "mean": 95,
        "stddev": 15,
        "min": 60,
        "max": 130
      },
      "flight_time_ms": {
        "mean": 145,
        "stddev": 25,
        "min": 90,
        "max": 200
      },
      "consistency": {
        "mean_stddev_ms": 22,
        "range": [15, 30],
        "description": "Natural human variation in timing"
      },
      "burst_pattern": {
        "mean_bursts_per_minute": 4.5,
        "mean_burst_duration_sec": 8.2,
        "mean_pause_duration_sec": 2.1
      },
      "error_correction": {
        "backspace_per_100_keys": 3.2,
        "correction_latency_ms": 420
      }
    },
    "time_of_day_patterns": {
      "morning_8_12": {"wpm": 58, "description": "Slower typing in morning"},
      "afternoon_12_18": {"wpm": 68, "description": "Fastest typing period"},
      "evening_18_24": {"wpm": 62, "description": "Moderate speed, more errors"}
    },
    "application_context": {
      "code_editor": {"wpm": 52, "pause_frequency": "high", "description": "Slower, thoughtful typing"},
      "email_browser": {"wpm": 70, "pause_frequency": "medium", "description": "Faster, flowing typing"},
      "chat_messaging": {"wpm": 75, "pause_frequency": "low", "description": "Rapid, burst-style typing"}
    }
  },
  "detection_thresholds": {
    "green_threshold": 85,
    "yellow_threshold": 70,
    "orange_threshold": 50,
    "red_threshold": 0,
    "bot_detection": {
      "consistency_stddev_threshold": 10,
      "impossible_wpm_threshold": 120,
      "perfect_timing_threshold": 5
    }
  },
  "file_metadata": {
    "format_version": "1.0",
    "generated_by": "KeyGuard AI v2.5.0",
    "generation_timestamp": "2026-01-20T15:30:00Z",
    "privacy_level": "timing_only",
    "can_reconstruct_keystrokes": false,
    "can_reconstruct_mouse_targets": false,
    "file_hash_sha256": "4f477879..."
  }
}
```

---

### B. Mouse Profile (`data/mouse_behavior.json`)

```json
{
  "export_metadata": {
    "export_timestamp": "2026-01-20T15:30:00Z",
    "software_version": "2.5.0",
    "data_type": "mouse_behavioral_baseline"
  },
  "mouse_profile": {
    "training_period": {
      "start_date": "2026-01-01T09:00:00Z",
      "end_date": "2026-01-15T18:30:00Z",
      "total_movements": 458234,
      "total_clicks": 12456
    },
    "movement_metrics": {
      "speed_px_per_sec": {
        "mean": 450,
        "stddev": 75,
        "min": 200,
        "max": 800
      },
      "curvature_index": {
        "mean": 1.20,
        "stddev": 0.15,
        "description": "Curved, human-like paths"
      },
      "micro_movements": {
        "corrections_per_sec": 8.5,
        "jitter_stddev_px": 2.3,
        "description": "Natural hand tremor"
      },
      "acceleration": {
        "mean_px_sec_squared": 52,
        "stddev": 28,
        "description": "Gradual speed changes"
      },
      "pause_behavior": {
        "pauses_per_minute": 15,
        "mean_pause_duration_ms": 1200,
        "description": "Frequent pauses for reading"
      }
    },
    "click_metrics": {
      "click_duration_ms": {
        "mean": 85,
        "stddev": 20,
        "min": 50,
        "max": 150
      },
      "double_click_timing_ms": {
        "mean": 180,
        "stddev": 25
      },
      "click_to_move_latency_ms": {
        "mean": 520,
        "stddev": 180,
        "description": "Reaction time after clicking"
      },
      "left_right_ratio": 15.2,
      "overshoot_frequency": 0.15,
      "overshoot_distance_px": 8.2
    },
    "scroll_metrics": {
      "lines_per_scroll": 3.2,
      "scroll_type": "continuous",
      "scroll_to_click_delay_ms": 780
    },
    "spatial_distribution": {
      "screen_zones_3x3": [
        [10, 15, 20],
        [12, 40, 18],
        [ 5, 10, 15]
      ],
      "dominant_zone": "center",
      "idle_position": "lower_right_corner"
    }
  },
  "file_metadata": {
    "format_version": "1.0",
    "generated_by": "KeyGuard AI v2.5.0",
    "generation_timestamp": "2026-01-20T15:30:00Z",
    "privacy_level": "motion_only",
    "can_reconstruct_keystrokes": false,
    "can_reconstruct_mouse_targets": false,
    "file_hash_sha256": "8b2341..."
  }
}
```

---

### C. Session Activity Export (`data/session_[timestamp].json`)

Exports rolling window data with $Z$-score deviations and flagged bot/anomalous events for security incident review.

---

### D. Comparison Report (`data/comparison_report.json`)

Provides side-by-side metric comparison, percentage differences, $Z$-scores, and security classification.

---

## 4. How to Export & Restore Profiles

1. **From GUI Dashboard**:
   * Navigate to the **Behavior** tab.
   * Scroll down to **Export Behavioral Data to JSON**.
   * Click any export button (`Export Keyboard Profile`, `Export Mouse Profile`, `Export Combined Profile`, etc.).
   * Select destination in the file save dialog.
2. **Profile Restoration**:
   * Stored profiles in `data/keyboard_behavior.json` and `data/mouse_behavior.json` can be loaded or backed up across machines.
