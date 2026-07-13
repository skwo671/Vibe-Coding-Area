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


def tesseract_is_available() -> bool:
    _configure_tesseract()
    try:
        pytesseract.get_tesseract_version()
        return True
    except pytesseract.TesseractNotFoundError:
        return False
    except Exception:
        return False


def tesseract_status_message() -> str:
    if tesseract_is_available():
        _configure_tesseract()
        cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
        return f"Tesseract: 已找到 ({cmd})"
    return (
        "Tesseract: 未找到。請安裝 https://github.com/UB-Mannheim/tesseract/wiki "
        "或設定環境變數 TESSERACT_CMD"
    )


def normalize_color_code(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 6:
        return value.strip()
    if "-" in value or " " in value:
        return f"{digits[:3]}-{digits[3:]}"
    return digits


def _ocr_text(image: np.ndarray) -> str:
    config_base = "-c tessedit_char_whitelist=0123456789- "
    texts: list[str] = []
    for psm in (6, 7, 11, 3):
        texts.append(pytesseract.image_to_string(image, config=f"--psm {psm} {config_base}"))
    return "\n".join(texts)


def _candidate_regions(image: np.ndarray) -> list[np.ndarray]:
    h, w = image.shape[:2]
    regions = [image]
    # Color cards often print the code along an edge or in a lower band.
    for y0, y1 in ((0, h // 3), (h // 3, 2 * h // 3), (2 * h // 3, h), (0, h // 4)):
        for x0, x1 in ((0, w // 2), (w // 2, w), (0, w)):
            crop = image[y0:y1, x0:x1]
            if crop.size > 0:
                regions.append(crop)
    return regions


def extract_color_code(path: Path) -> str | None:
    """OCR a color card code from an image, e.g. 654-980 or 000001."""
    _configure_tesseract()
    if not tesseract_is_available():
        return None

    image = cv2.imread(str(path))
    if image is None:
        return None

    candidates: list[str] = []
    try:
        for region in _candidate_regions(image):
            for variant in _preprocess_variants(region):
                text = _ocr_text(variant)
                candidates.extend(match.group(0) for match in COLOR_CODE_RE.finditer(text))
    except pytesseract.TesseractNotFoundError:
        return None
    except Exception:
        return None

    if not candidates:
        return None

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
