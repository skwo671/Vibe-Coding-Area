from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
SCAN_SKIP_DIRS = {"app", "models", ".venv", "__pycache__", ".git", "learn_bank"}

# Angle members in the simplified tool.
ANGLE_LABELS = {"AS", "FRONT", "SIDE", "CORNER"}
COLOR_LIGHTS = {"CWF", "D65", "UV"}

ANGLE_ALIAS = {
    "ACTUAL SIZE": "AS",
    "AS": "AS",
    "FRONT&BACK": "FRONT",
    "FRONT & BACK": "FRONT",
    "FRONT ON FABRIC": "FRONT",
    "FRONT": "FRONT",
    "SIDE VIEW": "SIDE",
    "SIDE": "SIDE",
    "CORNER": "CORNER",
}

TDS_MARKER = "_TDS"
PRODUCT_PREFIX_RE = re.compile(r"^\d{6}_[A-Z0-9]+G-\d{6}-\d{2}_.+?_\d+(?:ST|ND|RD|TH)$", re.I)

# Archroma / TCX style codes: 654-920, 19-1555, 000001, 654920
COLOR_CODE_RE = re.compile(
    r"(?<!\d)("
    r"\d{2,3}[-\s]?\d{3,4}"
    r"|"
    r"\d{6}"
    r")(?!\d)"
)


@dataclass(frozen=True)
class SimpleLabel:
    kind: str  # "angle" | "color"
    suffix: str  # AS | FRONT | CWF_654-920 | CWF_NAVY BLUE


def normalize_token(value: str) -> str:
    return " ".join(str(value).strip().split()).upper()


def sanitize_filename_part(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", value).strip()


def normalize_color_code(value: str) -> str:
    raw = str(value).strip().upper().replace(" ", "")
    digits = re.sub(r"\D", "", raw)
    if "-" in raw:
        left, right = raw.split("-", 1)
        left_d = re.sub(r"\D", "", left)
        right_d = re.sub(r"\D", "", right)
        if left_d and right_d:
            return f"{left_d}-{right_d}"
    if len(digits) == 6:
        # Prefer xxx-xxx when source looks hyphenated historically.
        return digits
    if len(digits) in {5, 7}:
        return digits
    return raw


def extract_color_codes_from_text(text: str) -> list[str]:
    found: list[str] = []
    for match in COLOR_CODE_RE.finditer(text or ""):
        code = normalize_color_code(match.group(1))
        if code and code not in found:
            found.append(code)
    return found


def prefix_from_tds_filename(path: Path) -> str | None:
    stem = path.stem
    idx = stem.upper().find(TDS_MARKER)
    if idx == -1:
        return None
    prefix = stem[:idx].rstrip("_")
    return prefix or None


def find_tds_prefix(folder: Path) -> str | None:
    counts: dict[str, int] = {}
    for path in folder.iterdir():
        if not path.is_file() or TDS_MARKER not in path.name.upper():
            continue
        prefix = prefix_from_tds_filename(path)
        if prefix:
            counts[prefix] = counts.get(prefix, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def parse_simple_label(stem: str) -> SimpleLabel | None:
    """Parse user-corrected or model filename stem into a simple label."""
    upper = stem.upper()
    # Strip mistaken _TDS_ middle segments.
    if f"{TDS_MARKER}_" in upper:
        stem = stem[upper.find(f"{TDS_MARKER}_") + len(TDS_MARKER) + 1 :]
        upper = stem.upper()

    for light in sorted(COLOR_LIGHTS, key=len, reverse=True):
        marker = f"_{light}_"
        idx = upper.rfind(marker)
        if idx != -1:
            color_part = stem[idx + len(marker) :]
            return SimpleLabel(kind="color", suffix=f"{light}_{sanitize_filename_part(color_part)}")

        bare = f"_{light}"
        if upper.endswith(bare):
            return SimpleLabel(kind="color", suffix=light)

    for label in (
        "ACTUAL SIZE",
        "FRONT ON FABRIC",
        "SIDE VIEW",
        "FRONT&BACK",
        "FRONT & BACK",
        "AS",
        "FRONT",
        "SIDE",
        "CORNER",
    ):
        marker = f"_{label}"
        if upper.endswith(marker) or upper.endswith(marker.replace(" ", "")):
            mapped = ANGLE_ALIAS[label]
            return SimpleLabel(kind="angle", suffix=mapped)

    # Bare color-code suffix: _654-920 / _19-1555
    m = re.search(r"_(\d{2,3}[- ]?\d{3,4}|\d{6})$", stem, re.I)
    if m:
        code = normalize_color_code(m.group(1))
        return SimpleLabel(kind="color", suffix=f"CWF_{code}")

    return None


def split_prefix_and_label(stem: str) -> tuple[str, SimpleLabel | None]:
    label = parse_simple_label(stem)
    if not label:
        return stem, None

    upper = stem.upper()
    suffix = label.suffix.upper()
    # Find last occurrence of suffix marker.
    for candidate in {suffix, suffix.replace("&", " & "), "ACTUAL SIZE", "SIDE VIEW", "FRONT&BACK"}:
        marker = f"_{candidate}"
        idx = upper.rfind(marker)
        if idx != -1:
            return stem[:idx].rstrip("_"), label
    return stem, label


def build_filename(prefix: str, suffix: str, extension: str) -> str:
    ext = extension if extension.startswith(".") else f".{extension}"
    suffix = sanitize_filename_part(normalize_token(suffix))
    prefix = prefix.strip().rstrip("_")
    if suffix:
        return f"{prefix}_{suffix}{ext}"
    return f"{prefix}{ext}"


def iter_image_paths(root: Path) -> list[Path]:
    root = root.resolve()
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if path.name.startswith("~$") or path.name == ".DS_Store":
            continue
        rel_parts = path.relative_to(root).parts[:-1]
        if SCAN_SKIP_DIRS.intersection(part.lower() for part in rel_parts):
            continue
        paths.append(path)
    return sorted(paths)
