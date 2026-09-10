"""
classifier.py
=============
Stage 3 of the pipeline: AI Classification Model.

Responsibilities:
  - Load a pre-trained scikit-learn model (Random Forest or Gradient
    Boosting) from disk, or fall back to a heuristic rule-based scorer
    when no model is available yet.
  - Accept a FeatureVector and return a ClassificationResult with:
      * risk_level  : RiskLevel enum  (SAFE / SUSPICIOUS / MALICIOUS)
      * score       : float in [0, 1] (probability of being malicious)
      * confidence  : float in [0, 1]
      * reasons     : list[str] forwarded from FeatureVector.active_indicators
  - Expose a batch_classify() method used by the pipeline loop.
  - Support hot-reloading the model file when it changes on disk (after
    retraining), so the running process picks up improvements without restart.

Model contract
--------------
  The serialised model must be a joblib-dumped dict::

      {
          "model"  : sklearn Pipeline (StandardScaler + classifier),
          "labels" : list[str]   # index → label name, e.g. ["safe","suspicious","malicious"]
          "version": str
          "trained_at": str  (ISO-8601)
      }

  Label index 0 = safe, 1 = suspicious, 2 = malicious.

Thresholds
----------
  SUSPICIOUS_THRESHOLD  = 0.35   (score ≥ this → at least SUSPICIOUS)
  MALICIOUS_THRESHOLD   = 0.70   (score ≥ this → MALICIOUS)
"""

from __future__ import annotations

import enum
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .feature_extractor import FeatureVector, FEATURE_NAMES, NUM_FEATURES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL_PATH = Path(__file__).parent.parent / "models" / "keylogger_detector.joblib"

SUSPICIOUS_THRESHOLD: float = 0.35
MALICIOUS_THRESHOLD: float  = 0.70

# How often (seconds) to poll for a changed model file on disk
MODEL_RELOAD_INTERVAL: float = 60.0


# ---------------------------------------------------------------------------
# Risk level enum
# ---------------------------------------------------------------------------

class RiskLevel(enum.Enum):
    SAFE       = "safe"
    SUSPICIOUS = "suspicious"
    MALICIOUS  = "malicious"

    @property
    def display_name(self) -> str:
        return self.value.upper()

    @property
    def emoji(self) -> str:
        return {"safe": "✅", "suspicious": "⚠️", "malicious": "🚨"}[self.value]


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    pid:        int
    name:       str
    exe:        Optional[str]
    risk_level: RiskLevel
    score:      float           # probability of malicious class, [0, 1]
    confidence: float           # max class probability
    reasons:    List[str]       # human-readable indicators
    timestamp:  float = field(default_factory=time.time)
    model_version: str = "heuristic"

    @property
    def is_threat(self) -> bool:
        return self.risk_level in (RiskLevel.SUSPICIOUS, RiskLevel.MALICIOUS)

    def summary(self) -> str:
        lvl = f"{self.risk_level.emoji} {self.risk_level.display_name}"
        reasons_txt = "; ".join(self.reasons) if self.reasons else "No specific indicators"
        return (
            f"[{lvl}] PID {self.pid} ({self.name}) "
            f"score={self.score:.2f}  —  {reasons_txt}"
        )


# ---------------------------------------------------------------------------
# Heuristic fallback scorer (no model required)
# ---------------------------------------------------------------------------

# Feature index helpers
_IDX: Dict[str, int] = {name: i for i, name in enumerate(FEATURE_NAMES)}


def _heuristic_score(features: np.ndarray) -> float:
    """
    Rule-based score in [0, 1] used when no trained model is available.
    Weights assigned based on security relevance of each feature.
    """
    score = 0.0

    # Strong signals (each worth more)
    if features[_IDX["has_ll_keyboard_hook"]] > 0:
        score += 0.40
    if features[_IDX["hook_no_window"]] > 0:
        score += 0.25
    if features[_IDX["hook_with_network"]] > 0:
        score += 0.20

    # Medium signals
    if features[_IDX["has_startup_entry"]] > 0:
        score += 0.15
    if features[_IDX["running_from_temp"]] > 0:
        score += 0.15
    if features[_IDX["no_exe_path"]] > 0:
        score += 0.10
    if features[_IDX["hook_api_present"]] > 0:
        score += 0.10
    if features[_IDX["hook_related_dll_count"]] >= 3:
        score += 0.10

    # Weaker signals
    if features[_IDX["net_bytes_sent_sum"]] > 500_000:
        score += 0.08
    if features[_IDX["file_write_rate"]] > 50_000:
        score += 0.05
    if features[_IDX["cmdline_empty"]] > 0 and features[_IDX["hook_api_present"]] > 0:
        score += 0.07

    # Mitigating factors (reduce score for benign traits)
    if features[_IDX["is_system_process"]] > 0:
        score -= 0.30
    if features[_IDX["has_visible_window"]] > 0:
        score -= 0.10
    if features[_IDX["is_signed"]] > 0:
        score -= 0.10

    return float(np.clip(score, 0.0, 1.0))


def _score_to_risk(score: float) -> RiskLevel:
    if score >= MALICIOUS_THRESHOLD:
        return RiskLevel.MALICIOUS
    if score >= SUSPICIOUS_THRESHOLD:
        return RiskLevel.SUSPICIOUS
    return RiskLevel.SAFE


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class KeyloggerClassifier:
    """
    Wraps a scikit-learn model (or falls back to heuristics) and scores
    FeatureVector objects.

    Usage::

        clf = KeyloggerClassifier()
        clf.load_model()          # optional — uses heuristics if missing
        results = clf.batch_classify(feature_vectors)
    """

    def __init__(self, model_path: Path = DEFAULT_MODEL_PATH) -> None:
        self._model_path = Path(model_path)
        self._model = None          # sklearn Pipeline or None
        self._labels: List[str] = ["safe", "suspicious", "malicious"]
        self._model_version: str = "heuristic"
        self._model_mtime: float = 0.0
        self._lock = threading.Lock()

        # Background thread for hot-reload
        self._reload_thread: Optional[threading.Thread] = None
        self._stop_reload = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_model(self) -> bool:
        """
        Attempt to load the serialised model from disk.
        Returns True on success, False if file doesn't exist yet.
        """
        return self._try_load()

    def start_hot_reload(self) -> None:
        """Start a background thread that watches the model file for changes."""
        self._reload_thread = threading.Thread(
            target=self._reload_loop,
            name="ModelReloader",
            daemon=True,
        )
        self._reload_thread.start()
        logger.debug("Model hot-reload watcher started.")

    def stop_hot_reload(self) -> None:
        self._stop_reload.set()

    def classify(self, fv: FeatureVector) -> ClassificationResult:
        """Score a single FeatureVector."""
        with self._lock:
            model = self._model
            labels = self._labels
            version = self._model_version

        score, confidence = self._compute_score(fv.features, model, labels)
        risk = _score_to_risk(score)

        return ClassificationResult(
            pid=fv.pid,
            name=fv.name,
            exe=fv.exe,
            risk_level=risk,
            score=score,
            confidence=confidence,
            reasons=fv.active_indicators,
            model_version=version,
        )

    def batch_classify(
        self, feature_vectors: List[FeatureVector]
    ) -> List[ClassificationResult]:
        """Score a batch of FeatureVectors efficiently."""
        if not feature_vectors:
            return []

        with self._lock:
            model = self._model
            labels = self._labels
            version = self._model_version

        results: List[ClassificationResult] = []

        if model is not None:
            # Batch inference via sklearn
            X = np.stack([fv.features for fv in feature_vectors])
            try:
                proba = model.predict_proba(X)   # shape (N, n_classes)
                for fv, prob_row in zip(feature_vectors, proba):
                    score, confidence = self._proba_to_score(prob_row, labels)
                    risk = _score_to_risk(score)
                    results.append(ClassificationResult(
                        pid=fv.pid,
                        name=fv.name,
                        exe=fv.exe,
                        risk_level=risk,
                        score=score,
                        confidence=confidence,
                        reasons=fv.active_indicators,
                        model_version=version,
                    ))
            except Exception as exc:
                logger.warning("Batch inference failed, falling back to heuristics: %s", exc)
                model = None   # fall through to heuristic path

        if model is None:
            for fv in feature_vectors:
                score = _heuristic_score(fv.features)
                confidence = max(score, 1.0 - score)
                risk = _score_to_risk(score)
                results.append(ClassificationResult(
                    pid=fv.pid,
                    name=fv.name,
                    exe=fv.exe,
                    risk_level=risk,
                    score=score,
                    confidence=confidence,
                    reasons=fv.active_indicators,
                    model_version="heuristic",
                ))

        return results

    @property
    def using_ml_model(self) -> bool:
        return self._model is not None

    @property
    def model_version(self) -> str:
        return self._model_version

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _try_load(self) -> bool:
        """Load / reload model from disk. Thread-safe."""
        if not self._model_path.exists():
            logger.info(
                "No model file found at %s — using heuristic scorer.",
                self._model_path,
            )
            return False
        try:
            import joblib
            data = joblib.load(self._model_path)
            model   = data["model"]
            labels  = data.get("labels", ["safe", "suspicious", "malicious"])
            version = data.get("version", "unknown")
            mtime   = self._model_path.stat().st_mtime

            with self._lock:
                self._model         = model
                self._labels        = labels
                self._model_version = version
                self._model_mtime   = mtime

            logger.info(
                "Loaded ML model v%s from %s (labels=%s).",
                version, self._model_path, labels,
            )
            return True
        except Exception as exc:
            logger.error("Failed to load model: %s", exc)
            return False

    def _reload_loop(self) -> None:
        while not self._stop_reload.is_set():
            self._stop_reload.wait(MODEL_RELOAD_INTERVAL)
            if self._stop_reload.is_set():
                break
            try:
                if self._model_path.exists():
                    mtime = self._model_path.stat().st_mtime
                    if mtime != self._model_mtime:
                        logger.info("Model file changed — reloading.")
                        self._try_load()
            except Exception as exc:
                logger.debug("Reload check error: %s", exc)

    def _compute_score(
        self,
        features: np.ndarray,
        model,
        labels: List[str],
    ) -> Tuple[float, float]:
        """Return (malicious_score, confidence) for a single feature vector."""
        if model is None:
            score = _heuristic_score(features)
            return score, max(score, 1.0 - score)

        try:
            proba = model.predict_proba(features.reshape(1, -1))[0]
            return self._proba_to_score(proba, labels)
        except Exception as exc:
            logger.warning("Model inference error: %s — using heuristic.", exc)
            score = _heuristic_score(features)
            return score, max(score, 1.0 - score)

    @staticmethod
    def _proba_to_score(
        proba: np.ndarray,
        labels: List[str],
    ) -> Tuple[float, float]:
        """
        Convert a probability row into (malicious_score, confidence).

        malicious_score = P(malicious) + 0.5 * P(suspicious)
        confidence      = max class probability
        """
        label_lower = [l.lower() for l in labels]
        p_malicious  = proba[label_lower.index("malicious")] if "malicious"  in label_lower else 0.0
        p_suspicious = proba[label_lower.index("suspicious")] if "suspicious" in label_lower else 0.0

        score      = float(np.clip(p_malicious + 0.5 * p_suspicious, 0.0, 1.0))
        confidence = float(np.max(proba))
        return score, confidence
