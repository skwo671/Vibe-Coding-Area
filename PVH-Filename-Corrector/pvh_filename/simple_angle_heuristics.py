from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from pvh_filename.simple_as import _corr


def looks_like_side_view(path: Path) -> bool:
    """Wide frame with dissimilar left/right halves (not AS duplicate)."""
    image = cv2.imread(str(path))
    if image is None:
        return False
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if w / max(h, 1) < 1.2:
        return False
    mid = w // 2
    return _corr(gray[:, :mid], gray[:, w - mid :]) < 0.35


def looks_like_corner(path: Path) -> bool:
    """
    Corner shots tend to show a compact product near edges / asymmetric crop.
    Weak heuristic — angle model should override when available.
    """
    image = cv2.imread(str(path))
    if image is None:
        return False
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if min(h, w) < 80:
        return False

    # Content mass more toward one corner than center.
    ys, xs = np.where(gray < np.percentile(gray, 40))
    if len(xs) < 50:
        return False
    cx, cy = xs.mean() / w, ys.mean() / h
    dist_center = ((cx - 0.5) ** 2 + (cy - 0.5) ** 2) ** 0.5
    return dist_center > 0.18 and w / max(h, 1) < 1.35
