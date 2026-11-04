"""Coarse ECG contact quality, used by the live view and session summaries.

This is a pre-analysis heuristic: it flags a missing/loose electrode (flat or tiny signal),
saturation and heavy noise. The analysis stage replaces it with a proper per-beat measure.
"""
from __future__ import annotations

import numpy as np

GOOD, FAIR, POOR, NONE = "good", "fair", "poor", "none"


def window_quality(uv: np.ndarray) -> str:
    """Classify a window of ECG (µV, ~2-10 s at 130 Hz)."""
    if len(uv) < 64:
        return NONE
    x = uv.astype(np.float64)
    x = x - np.median(x)
    lo, hi = np.percentile(x, [1, 99])
    span = hi - lo
    if span < 150:  # electrode off: H10 outputs near-flat signal
        return NONE
    if span > 8000 or np.mean(np.abs(x) > 15000) > 0.01:
        return POOR
    # High-frequency noise relative to the QRS amplitude.
    d = np.diff(x)
    noise = np.median(np.abs(d)) / span
    # Baseline wander: spread of 1 s medians relative to amplitude.
    sec = len(x) // 130
    wander = 0.0
    if sec >= 2:
        meds = np.median(x[: sec * 130].reshape(sec, 130), axis=1)
        wander = (meds.max() - meds.min()) / span
    if noise < 0.035 and wander < 0.6:
        return GOOD
    if noise < 0.07 and wander < 1.2:
        return FAIR
    return POOR


SCORE = {GOOD: 1.0, FAIR: 0.6, POOR: 0.15, NONE: 0.0}
