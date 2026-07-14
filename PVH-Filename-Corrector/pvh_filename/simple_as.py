from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _resize(gray: np.ndarray, size: int = 256) -> np.ndarray:
    return cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = _resize(a).astype(np.float32)
    b = _resize(b).astype(np.float32)
    a = (a - a.mean()) / (a.std() + 1e-6)
    b = (b - b.mean()) / (b.std() + 1e-6)
    return float(np.mean(a * b))


def _template(a: np.ndarray, b: np.ndarray) -> float:
    best = 0.0
    h, w = a.shape[:2]
    for scale in (0.3, 0.35, 0.4, 0.45, 0.5, 0.55):
        th, tw = max(24, int(h * scale)), max(24, int(w * scale))
        tmpl = a[:th, :tw]
        if tmpl.shape[0] >= b.shape[0] or tmpl.shape[1] >= b.shape[1]:
            continue
        score = float(cv2.matchTemplate(b, tmpl, cv2.TM_CCOEFF_NORMED).max())
        best = max(best, score)
    return best


def has_two_similar_products(path: Path) -> bool:
    """
    Actual Size (AS): image contains two very similar product patterns.

    Side-by-side / top-bottom duplicates of the same trim/label.
    """
    image = cv2.imread(str(path))
    if image is None:
        return False

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    h, w = gray.shape[:2]
    if h < 120 or w < 200:
        return False

    mw, mh = w // 2, h // 2
    pairs = [
        (gray[:, :mw], gray[:, w - mw :]),
        (gray[:mh, :], gray[h - mh :, :]),
    ]

    for left, right in pairs:
        corr = _corr(left, right)
        tmpl = max(_template(left, right), _template(right, left))
        # Very similar local copies with differing backgrounds.
        if tmpl >= 0.72 and corr < 0.35:
            return True
        # Near-identical mirrored halves.
        if tmpl >= 0.92 and corr >= 0.85:
            return True
    return False
