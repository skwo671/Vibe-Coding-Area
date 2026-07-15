from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from pvh_filename.simple_labels import extract_color_codes_from_text, normalize_color_code

_TESSERACT_CONFIGURED = False

# Archroma codes on cards: 654-920, 104-850, 658-170
ARCHROMA_CODE_RE = re.compile(r"(?<!\d)(\d{3})\s*[-–—]\s*(\d{3})(?!\d)")
# Name + code on same/nearby lines, e.g. DESERT SKY 654-920 / WHITE 658-170
NAME_CODE_RE = re.compile(
    r"([A-Z][A-Z0-9 /&'-]{1,40}?)\s+(\d{3})\s*[-–—]\s*(\d{3})",
    re.I,
)
CWF_LABEL_RE = re.compile(r"\bC\s*W\s*F\b", re.I)


@dataclass(frozen=True)
class ColorCardOCR:
    color_code: str
    has_cwf_label: bool
    light_source: str  # "CWF" or "D65"
    color_name: str = ""


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


def _ocr_text(image: np.ndarray, config: str) -> str:
    try:
        return pytesseract.image_to_string(image, config=config) or ""
    except Exception:
        return ""


def _has_cwf_label(text: str) -> bool:
    compact = re.sub(r"[\s\-_.]", "", text.upper())
    return "CWF" in compact or bool(CWF_LABEL_RE.search(text))


def _collect_codes(text: str) -> list[str]:
    found: list[str] = []
    for match in ARCHROMA_CODE_RE.finditer(text or ""):
        code = f"{match.group(1)}-{match.group(2)}"
        if code not in found:
            found.append(code)
    for code in extract_color_codes_from_text(text or ""):
        # Prefer normalized xxx-xxx when 6 digits.
        digits = re.sub(r"\D", "", code)
        if len(digits) == 6:
            pretty = f"{digits[:3]}-{digits[3:]}"
            if pretty not in found:
                found.append(pretty)
        elif code not in found:
            found.append(normalize_color_code(code))
    return found


def _collect_named_codes(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for match in NAME_CODE_RE.finditer(text or ""):
        name = re.sub(r"\s+", " ", match.group(1)).strip(" -_/").upper()
        code = f"{match.group(2)}-{match.group(3)}"
        if name and "ARCHROMA" not in name and "LIFE" not in name and "SHOP" not in name:
            pairs.append((code, name))
    return pairs


def _enhance_for_grey_text(gray: np.ndarray) -> list[np.ndarray]:
    """Boost low-contrast grey text on white Archroma headers."""
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    eq = clahe.apply(gray)
    blur = cv2.GaussianBlur(eq, (3, 3), 0)
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    # Emphasize darker glyphs on bright background.
    dark = cv2.normalize(255 - gray, None, 0, 255, cv2.NORM_MINMAX)
    _, dark_bin = cv2.threshold(dark, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((2, 2), np.uint8)
    return [
        gray,
        eq,
        otsu,
        cv2.bitwise_not(otsu),
        adaptive,
        cv2.bitwise_not(adaptive),
        dark_bin,
        cv2.morphologyEx(dark_bin, cv2.MORPH_CLOSE, kernel),
    ]


def _header_regions(image: np.ndarray) -> list[np.ndarray]:
    """Prefer top white Archroma card header; also scan bright blobs."""
    h, w = image.shape[:2]
    regions = [
        image[: max(80, int(h * 0.28)), :],
        image[: max(80, int(h * 0.38)), :],
        image[: max(80, int(h * 0.50)), :],
        image,
    ]

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    # Bright / near-white paper.
    mask = cv2.inRange(hsv, (0, 0, 180), (179, 70, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        area = bw * bh
        if area < (h * w) * 0.01 or bw < w * 0.2:
            continue
        boxes.append((area, x, y, bw, bh))
    boxes.sort(reverse=True)
    for _, x, y, bw, bh in boxes[:4]:
        pad = 8
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
        crop = image[y0:y1, x0:x1]
        if min(crop.shape[:2]) > 30:
            regions.append(crop)
    return regions


def _scale(gray: np.ndarray) -> np.ndarray:
    # Make header text large enough for Tesseract.
    target = 1400
    scale = max(2.0, target / max(gray.shape[1], 1))
    scale = min(scale, 4.0)
    return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def _detect_cwf_stickers(image: np.ndarray) -> bool:
    """Look for standalone CWF labels (often a separate white sticker)."""
    h, w = image.shape[:2]
    upper = image[: max(120, int(h * 0.45)), :]
    uh, uw = upper.shape[:2]
    hsv = cv2.cvtColor(upper, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 0, 190), (179, 60, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    configs = ["--psm 8", "--psm 7", "--psm 6"]
    crops = [upper]
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw < 40 or bh < 20 or bw * bh < 800:
            continue
        aspect = bw / max(bh, 1)
        if aspect < 1.2 or aspect > 8:
            continue
        crops.append(upper[y : y + bh, x : x + bw])

    for crop in crops:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = _scale(gray)
        for variant in _enhance_for_grey_text(gray)[:4]:
            for config in configs:
                text = _ocr_text(variant, config)
                if _has_cwf_label(text):
                    return True
    # Whole-image fallback for large CWF glyphs.
    full = _ocr_text(_scale(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)), "--psm 11")
    return _has_cwf_label(full)


def detect_color_card(path: Path) -> ColorCardOCR | None:
    """
    Detect Archroma fabric color-card info.

    Rule:
      - color code + CWF label  → CWF
      - color code without CWF  → D65
    """
    _configure_tesseract()
    if not tesseract_is_available():
        return None

    image = cv2.imread(str(path))
    if image is None:
        return None

    candidates: list[str] = []
    named: list[tuple[str, str]] = []
    configs = [
        "--psm 6",
        "--psm 4",
        "--psm 11",
        "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- ",
        "--psm 6 -c tessedit_char_whitelist=0123456789-",
    ]

    try:
        saw_cwf = _detect_cwf_stickers(image)
        for region in _header_regions(image):
            gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            gray = _scale(gray)
            for variant in _enhance_for_grey_text(gray):
                for config in configs:
                    text = _ocr_text(variant, config)
                    if not text.strip():
                        continue
                    if _has_cwf_label(text):
                        saw_cwf = True
                    # Join lines so "DESERT SKY" + "654-920" can match together.
                    joined = re.sub(r"\s+", " ", text.upper())
                    candidates.extend(_collect_codes(text))
                    candidates.extend(_collect_codes(joined))
                    named.extend(_collect_named_codes(joined))
    except Exception:
        return None

    if not candidates and not named:
        return None

    color_name = ""
    if named:
        named.sort(key=lambda item: (len(item[1]) > 24, -len(item[1])))
        code, color_name = named[0]
    else:
        candidates = list(dict.fromkeys(candidates))
        candidates.sort(key=lambda c: (not bool(re.fullmatch(r"\d{3}-\d{3}", c)), c))
        code = candidates[0]

    light = "CWF" if saw_cwf else "D65"
    return ColorCardOCR(
        color_code=code,
        has_cwf_label=saw_cwf,
        light_source=light,
        color_name=color_name,
    )


def detect_color_card_code(path: Path) -> str | None:
    result = detect_color_card(path)
    return result.color_code if result else None
