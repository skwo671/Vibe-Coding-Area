from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from pvh_filename.simple_labels import COLOR_CODE_RE, extract_color_codes_from_text, normalize_color_code

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
    except Exception:
        return False


def tesseract_status_message() -> str:
    if tesseract_is_available():
        cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
        return f"Tesseract: 已找到 ({cmd})"
    return "Tesseract: 未找到（對色相 OCR 需要安裝）"


def _ocr_text(image: np.ndarray) -> str:
    configs = [
        "--psm 6 -c tessedit_char_whitelist=0123456789-",
        "--psm 7 -c tessedit_char_whitelist=0123456789-",
        "--psm 11 -c tessedit_char_whitelist=0123456789-",
        "--psm 6",
    ]
    texts: list[str] = []
    for config in configs:
        try:
            texts.append(pytesseract.image_to_string(image, config=config))
        except Exception:
            continue
    return "\n".join(texts)


def _regions(image: np.ndarray) -> list[np.ndarray]:
    h, w = image.shape[:2]
    bands = [
        image,
        image[int(h * 0.4) :, :],
        image[int(h * 0.55) :, :],
        image[: int(h * 0.45), :],
        image[:, : w // 2],
        image[:, w // 2 :],
    ]
    return [b for b in bands if b.size > 0 and min(b.shape[:2]) > 20]


def _variants(region: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if region.ndim == 3 else region
    scale = 3 if max(gray.shape[:2]) < 2800 else 2
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    denoised = cv2.bilateralFilter(gray, 7, 50, 50)
    _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 8
    )
    return [gray, denoised, otsu, cv2.bitwise_not(otsu), adaptive, cv2.bitwise_not(adaptive)]


def detect_color_card_code(path: Path) -> str | None:
    """Return color code if a fabric color card number is visible."""
    _configure_tesseract()
    if not tesseract_is_available():
        return None

    image = cv2.imread(str(path))
    if image is None:
        return None

    candidates: list[str] = []
    try:
        for region in _regions(image):
            for variant in _variants(region):
                text = _ocr_text(variant)
                candidates.extend(extract_color_codes_from_text(text))
                # Also catch codes glued by OCR without separators via raw regex.
                candidates.extend(
                    normalize_color_code(m.group(0))
                    for m in COLOR_CODE_RE.finditer(re.sub(r"\s+", " ", text))
                )
    except Exception:
        return None

    if not candidates:
        return None

    # Prefer hyphenated codes (654-920 / 19-1555) over plain 6-digit.
    candidates = list(dict.fromkeys(candidates))
    candidates.sort(key=lambda c: (("-" not in c), len(c), c))
    return candidates[0]
