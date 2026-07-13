from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _prepare_region(region: np.ndarray, size: int = 256) -> np.ndarray:
    return cv2.resize(region, (size, size), interpolation=cv2.INTER_AREA)


def _correlation_score(a: np.ndarray, b: np.ndarray) -> float:
    a = _prepare_region(a).astype(np.float32)
    b = _prepare_region(b).astype(np.float32)
    a = (a - a.mean()) / (a.std() + 1e-6)
    b = (b - b.mean()) / (b.std() + 1e-6)
    return float(np.mean(a * b))


def _multiscale_template_score(source: np.ndarray, target: np.ndarray) -> float:
    """Find the best template match when a scaled crop of source appears in target."""
    best = 0.0
    height, width = source.shape[:2]
    if height < 40 or width < 40:
        return 0.0

    for scale in (0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55):
        crop_h = max(24, int(height * scale))
        crop_w = max(24, int(width * scale))
        template = source[:crop_h, :crop_w]
        if template.size == 0 or template.shape[0] > target.shape[0] or template.shape[1] > target.shape[1]:
            continue
        result = cv2.matchTemplate(target, template, cv2.TM_CCOEFF_NORMED)
        best = max(best, float(result.max()))
    return best


def _pair_duplicate_score(a: np.ndarray, b: np.ndarray) -> float:
    corr = _correlation_score(a, b)
    tmpl = max(_multiscale_template_score(a, b), _multiscale_template_score(b, a))
    # Two repeated labels side-by-side: local match is strong, global halves differ.
    if 0.68 <= tmpl <= 0.82 and corr < 0.15:
        return tmpl
    # Near-perfect mirrored copies.
    if tmpl >= 0.95 and corr >= 0.9:
        return (tmpl + corr) / 2.0
    return 0.0


def _best_half_match(gray: np.ndarray) -> float:
    height, width = gray.shape[:2]
    if height < 120 or width < 240:
        return 0.0

    mid_w = width // 2
    mid_h = height // 2
    scores = [
        _pair_duplicate_score(gray[:, :mid_w], gray[:, width - mid_w :]),
        _pair_duplicate_score(gray[:mid_h, :], gray[height - mid_h :, :]),
    ]
    return max(scores)


def has_duplicate_pattern(path: Path) -> bool:
    """
    Detect Actual Size photos: two visually identical patterns in one image.

    Typical layout: the same label/trim shown twice side-by-side or top-bottom.
    """
    image = cv2.imread(str(path))
    if image is None:
        return False

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    return _best_half_match(gray) > 0.0
