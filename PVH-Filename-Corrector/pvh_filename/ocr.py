from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract

COLOR_CODE_RE = re.compile(r"(?<!\d)(?:\d{3}[-\s]?\d{3}|\d{6})(?!\d)")
DIGIT_RUN_RE = re.compile(r"\d{3,6}")

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


def _ocr_text(image: np.ndarray, *, digits_only: bool = True) -> str:
    whitelist = "-c tessedit_char_whitelist=0123456789- " if digits_only else ""
    texts: list[str] = []
    for psm in (6, 7, 8, 11, 13, 3):
        texts.append(pytesseract.image_to_string(image, config=f"--psm {psm} {whitelist}".strip()))
    return "\n".join(texts)


def _candidate_regions(image: np.ndarray) -> list[np.ndarray]:
    height, width = image.shape[:2]
    regions = [image]
    bands = (
        (0, height),
        (int(height * 0.35), height),
        (int(height * 0.45), height),
        (int(height * 0.55), height),
        (0, int(height * 0.55)),
        (height // 4, 3 * height // 4),
    )
    for y0, y1 in bands:
        for x0, x1 in ((0, width), (0, width // 2), (width // 2, width), (width // 4, 3 * width // 4)):
            crop = image[y0:y1, x0:x1]
            if crop.size > 0 and crop.shape[0] > 20 and crop.shape[1] > 20:
                regions.append(crop)
    return regions


def _preprocess_variants(image: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    scale = 3 if max(gray.shape[:2]) < 3000 else 2
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    variants = [gray]
    denoised = cv2.bilateralFilter(gray, 9, 75, 75)
    variants.append(denoised)

    for src in (gray, denoised):
        _, otsu = cv2.threshold(src, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.extend([otsu, cv2.bitwise_not(otsu)])
        adaptive = cv2.adaptiveThreshold(
            src, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
        )
        variants.extend([adaptive, cv2.bitwise_not(adaptive)])

    kernel = np.ones((2, 2), np.uint8)
    for variant in list(variants):
        variants.append(cv2.morphologyEx(variant, cv2.MORPH_CLOSE, kernel))

    return variants


def _extract_codes_from_text(text: str) -> list[str]:
    found: list[str] = []
    for match in COLOR_CODE_RE.finditer(text):
        found.append(match.group(0))
    if found:
        return found
    for match in DIGIT_RUN_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) == 6:
            found.append(digits)
    return found


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
                for digits_only in (True, False):
                    text = _ocr_text(variant, digits_only=digits_only)
                    candidates.extend(_extract_codes_from_text(text))
    except pytesseract.TesseractNotFoundError:
        return None
    except Exception:
        return None

    if not candidates:
        return None

    candidates.sort(key=lambda c: ("-" not in c and " " not in c, c))
    return normalize_color_code(candidates[0])
