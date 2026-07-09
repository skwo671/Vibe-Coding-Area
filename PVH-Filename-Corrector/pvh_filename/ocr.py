from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract


COLOR_CODE_RE = re.compile(r"(?<!\d)(?:\d{3}[-\s]?\d{3}|\d{6})(?!\d)")

_TESSERACT_CONFIGURED = False


def _configure_tesseract() -> None:
    global _TESSERACT_CONFIGURED
    if _TESSERACT_CONFIGURED:
        return
    _TESSERACT_CONFIGURED = True

    env_cmd = Path(os.environ["TESSERACT_CMD"]) if "TESSERACT_CMD" in os.environ else None
    if env_cmd and env_cmd.exists():
        pytesseract.pytesseract.tesseract_cmd = str(env_cmd)
        return

    if sys.platform == "win32":
        for candidate in (
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        ):
            if candidate.exists():
                pytesseract.pytesseract.tesseract_cmd = str(candidate)
                return


def normalize_color_code(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 6:
        return value.strip()
    if "-" in value or " " in value:
        return f"{digits[:3]}-{digits[3:]}"
    return digits


def extract_color_code(path: Path) -> str | None:
    """OCR a color card code from an image, e.g. 654-980 or 000001."""
    _configure_tesseract()
    image = cv2.imread(str(path))
    if image is None:
        return None

    candidates: list[str] = []
    variants = _preprocess_variants(image)
    config = "--psm 6 -c tessedit_char_whitelist=0123456789- "

    for variant in variants:
        text = pytesseract.image_to_string(variant, config=config)
        candidates.extend(match.group(0) for match in COLOR_CODE_RE.finditer(text))

    if not candidates:
        return None

    # Prefer explicit hyphenated card codes over plain six-digit codes.
    candidates.sort(key=lambda c: ("-" not in c and " " not in c, c))
    return normalize_color_code(candidates[0])


def _preprocess_variants(image: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scale = 2 if max(gray.shape[:2]) < 2500 else 1
    if scale > 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    denoised = cv2.bilateralFilter(gray, 9, 75, 75)
    _, threshold = cv2.threshold(
        denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    inverted = cv2.bitwise_not(threshold)
    return [gray, threshold, inverted]
