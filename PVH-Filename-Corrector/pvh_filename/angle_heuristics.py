from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path

import cv2
import numpy as np

from pvh_filename.actual_size import _correlation_score, has_duplicate_pattern
from pvh_filename.filenames import (
    ACTUAL_SIZE_LABELS,
    FRONT_BACK_LABELS,
    SIDE_VIEW_LABELS,
    format_angle_suffix,
    normalize_token,
)

if TYPE_CHECKING:
    from pvh_filename.model import HierarchicalClassifier


def looks_like_side_view(path: Path) -> bool:
    """Heuristic: wide product shot with different left/right halves (not duplicate)."""
    image = cv2.imread(str(path))
    if image is None:
        return False

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    if width / max(height, 1) < 1.15:
        return False
    if has_duplicate_pattern(path):
        return False

    mid = width // 2
    corr = _correlation_score(gray[:, :mid], gray[:, width - mid :])
    return corr < 0.35


def _class_prob(classes: list[str], probs: np.ndarray, labels: set[str]) -> float:
    score = 0.0
    for idx, label in enumerate(classes):
        if normalize_token(label) in labels:
            score = max(score, float(probs[idx]))
    return score


def resolve_angle_suffix(
    path: Path,
    model_suffix: str,
    classifier: HierarchicalClassifier,
    embedding: np.ndarray,
) -> tuple[str, str]:
    """Pick angle suffix with duplicate-pattern and side-view heuristics."""
    if has_duplicate_pattern(path):
        return "AS", "duplicate_pattern"

    classes = [str(c) for c in getattr(classifier.angle_encoder, "classes_", [])]
    if not classes or embedding.size == 0:
        return format_angle_suffix(model_suffix), "model"

    probs = classifier.angle_model.predict_proba(embedding.reshape(1, -1))[0]
    model_view = normalize_token(model_suffix)

    if model_view in ACTUAL_SIZE_LABELS or _class_prob(classes, probs, ACTUAL_SIZE_LABELS) >= 0.12:
        return "AS", "model_actual_size"

    side_prob = _class_prob(classes, probs, SIDE_VIEW_LABELS)
    front_prob = _class_prob(classes, probs, FRONT_BACK_LABELS)

    if side_prob >= 0.1 and (
        side_prob >= front_prob * 0.4
        or model_view in SIDE_VIEW_LABELS
        or looks_like_side_view(path)
    ):
        return "SIDE", "model_side" if side_prob >= front_prob else "heuristic_side"

    if model_view in FRONT_BACK_LABELS or front_prob >= 0.1:
        if looks_like_side_view(path):
            return "SIDE", "heuristic_side"
        return "FRONT", "model_front"

    return format_angle_suffix(model_suffix), "model"
