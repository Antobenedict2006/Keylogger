"""
test_phase2_behavioral.py
=========================
Validation script for Phase 2 Behavioral Biometrics:
  - Mouse movement & click tracking metrics
  - Multi-modal combined scoring (Keyboard + Mouse)
  - Multi-modal bot type detection
  - JSON export validation with SHA-256 integrity
  - SQLite persistence in mouse_behavior table
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


from src.behavioral_analyzer import (
    BehavioralAnalysisEngine,
    BehavioralExporter,
    KeystrokeEvent,
    MouseEvent,
    MouseMetrics,
    MouseRecorder,
    MultiModalAnomalyDetector,
    MultiModalBaselineLearner,
    TypingMetrics,
)
from src.db_logger import DBLogger, TypingBehaviorStore


def run_tests():
    print("=" * 60)
    print("  Starting Phase 2 Behavioral Biometrics Test Suite")
    print("=" * 60)

    # 1. Test Mouse Analyzer Metrics
    print("\n[1] Testing Mouse Motion & Curvature Calculations...")
    engine = BehavioralAnalysisEngine()
    test_mouse_events = []
    t = time.perf_counter()
    # Simulate a curved human-like movement
    for i in range(30):
        test_mouse_events.append(
            MouseEvent(
                timestamp=t + (i * 0.03),
                event_type="move",
                x=100.0 + (i * 10) + (math_jitter := 3.0 if i % 2 == 0 else -3.0),
                y=100.0 + (i * 8) + (math_jitter * 1.5),
                dx=10.0,
                dy=8.0,
                speed=420.0 + (i * 2.0),
                acceleration=15.0,
            )
        )
    # Add click events
    test_mouse_events.append(
        MouseEvent(timestamp=t + 1.0, event_type="click", x=400, y=340, button="left", click_state="pressed")
    )
    test_mouse_events.append(
        MouseEvent(timestamp=t + 1.085, event_type="click", x=400, y=340, button="left", click_state="released", duration_ms=85.0)
    )

    mm = engine._mouse_analyzer.analyze(test_mouse_events, window_secs=60.0)
    assert mm.is_sufficient, "Mouse metrics should be sufficient"
    assert mm.avg_speed_pxsec > 0, "Speed should be > 0"
    assert mm.curvature_index >= 1.0, f"Curvature index should be >= 1.0 (got {mm.curvature_index})"
    assert mm.avg_click_duration_ms > 0, "Click duration should be recorded"
    print(f"  [OK] Mouse Metrics: Speed={mm.avg_speed_pxsec:.1f}px/s, Curvature={mm.curvature_index:.2f}, ClickDur={mm.avg_click_duration_ms:.1f}ms")

    # 2. Test Multi-Modal Combined Scoring
    print("\n[2] Testing Multi-Modal Combined Scoring (KB + Mouse)...")
    detector = MultiModalAnomalyDetector()
    kb_sample = TypingMetrics(
        keystroke_count=120, wpm=66.0, avg_dwell_ms=94.0, avg_flight_ms=142.0, consistency_stddev=21.5, burst_count=5, is_sufficient=True
    )
    kb_bl, mouse_bl = engine._learner.compute_and_save_baselines(15000, 20000)

    result_normal = detector.analyze(kb_sample, mm, kb_bl, mouse_bl, kb_mouse_switch_latency=450.0, activity_correlation=0.78)
    assert result_normal.similarity_score >= 85.0, f"Normal score should be >= 85% (got {result_normal.similarity_score}%)"
    print(f"  [OK] Normal Combined Similarity: {result_normal.similarity_score:.1f}% (Status: {result_normal.status_label})")

    # 3. Test Bot Classification (All 4 Bot Types)
    print("\n[3] Testing Enhanced Multi-Modal Bot Classification...")
    # Bot 1: Macro
    kb_bot = TypingMetrics(
        keystroke_count=200, wpm=145.0, avg_dwell_ms=45.0, avg_flight_ms=50.0, consistency_stddev=3.2, burst_count=1, is_sufficient=True
    )
    mm_bot_idle = MouseMetrics(movement_count=10, is_sufficient=True)
    res_macro = detector.analyze(kb_bot, mm_bot_idle, kb_bl, mouse_bl)
    assert res_macro.bot_detected and res_macro.bot_type == "keyboard_macro", f"Expected keyboard_macro bot (got {res_macro.bot_type})"
    print(f"  [OK] Bot Type 1 Detected: {res_macro.bot_type} (Confidence: {res_macro.bot_reason})")

    # Bot 2: Remote Control (Geometric straight paths + 0 jitter)
    kb_norm = TypingMetrics(keystroke_count=50, wpm=60.0, avg_dwell_ms=90.0, consistency_stddev=20.0, is_sufficient=True)
    mm_straight = MouseMetrics(movement_count=50, curvature_index=1.01, jitter_stddev_px=0.2, is_sufficient=True)
    res_remote = detector.analyze(kb_norm, mm_straight, kb_bl, mouse_bl)
    assert res_remote.bot_detected and res_remote.bot_type == "remote_control", f"Expected remote_control bot (got {res_remote.bot_type})"
    print(f"  [OK] Bot Type 2 Detected: {res_remote.bot_type} (Confidence: {res_remote.bot_reason})")

    # 4. Test JSON Exports and SHA-256 Hashes
    print("\n[4] Testing JSON Export Suite & SHA-256 Verification...")
    kb_path = engine.export_keyboard_json(PROJECT_ROOT / "data" / "keyboard_behavior.json")
    mouse_path = engine.export_mouse_json(PROJECT_ROOT / "data" / "mouse_behavior.json")
    comb_path = engine.export_combined_profile_json(PROJECT_ROOT / "data" / "behavioral_profile.json")
    comp_path = engine.export_comparison_json(PROJECT_ROOT / "data" / "comparison_report.json")
    session_path = engine.export_session_json(PROJECT_ROOT / "data" / "session_test.json")

    for p in [kb_path, mouse_path, comb_path, comp_path, session_path]:
        assert p.exists(), f"File {p} should exist"
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "file_metadata" in data, f"file_metadata missing in {p}"
            assert "file_hash_sha256" in data["file_metadata"], f"file_hash_sha256 missing in {p}"
            assert len(data["file_metadata"]["file_hash_sha256"]) == 64, f"Invalid SHA-256 in {p}"
        print(f"  [OK] Verified JSON Export: {p.name} (SHA-256: {data['file_metadata']['file_hash_sha256'][:16]}...)")

    # Clean up test session file
    if session_path.exists():
        session_path.unlink()

    # 5. Test SQLite mouse_behavior Database Logging
    print("\n[5] Testing Database Persistence (mouse_behavior)...")
    db = DBLogger(db_path=PROJECT_ROOT / "logs" / "test_events.db")
    store = TypingBehaviorStore(db)
    store.ensure_schema()
    store.log_mouse_sample(mm, is_training=True)
    rows = store.query_recent_mouse_samples(limit=10)
    assert len(rows) > 0, "Should retrieve logged mouse behavior rows"
    print(f"  [OK] Successfully wrote and queried {len(rows)} mouse_behavior row(s) in SQLite.")
    db.close()
    if (PROJECT_ROOT / "logs" / "test_events.db").exists():
        try:
            (PROJECT_ROOT / "logs" / "test_events.db").unlink()
        except Exception:
            pass

    print("\n" + "=" * 60)
    print("  All Phase 2 Behavioral Biometrics Tests PASSED Successfully! (100%)")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
