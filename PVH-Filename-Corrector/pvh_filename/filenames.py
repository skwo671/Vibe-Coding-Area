from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
REFERENCE_EXTENSIONS = {".pdf", ".xls", ".xlsm", ".xlsx", ".doc", ".docx"} | IMAGE_EXTENSIONS

# Skip tool/runtime folders when scanning a portable package root.
SCAN_SKIP_DIRS = {"app", "models", ".venv", "__pycache__", ".git"}

# Longest-first so multi-word view types match correctly.
VIEW_TYPES = [
    "FRONT ON FABRIC",
    "FRONT & BACK",
    "FRONT&BACK",
    "SIDE VIEW",
    "ACTUAL SIZE",
    "AS",
    "CORNER",
    "CWF",
    "D65",
    "UV",
    "TDS",
]

ANGLE_VIEWS = {
    "CORNER",
    "SIDE VIEW",
    "FRONT&BACK",
    "FRONT & BACK",
    "FRONT ON FABRIC",
    "ACTUAL SIZE",
    "AS",
}

ACTUAL_SIZE_LABELS = {"ACTUAL SIZE", "AS"}
FRONT_BACK_LABELS = {"FRONT&BACK", "FRONT & BACK"}
SIDE_VIEW_LABELS = {"SIDE VIEW", "SIDE"}

PRODUCT_PREFIX_RE = re.compile(r"^\d{6}_[A-Z0-9]+G-\d{6}-\d{2}_.+?_\d+(?:ST|ND|RD|TH)$")
TDS_MARKER = "_TDS"
COLOR_VIEWS = {"CWF", "D65", "UV"}


@dataclass(frozen=True)
class ParsedFilename:
    product_prefix: str
    suffix: str
    extension: str

    @property
    def stem(self) -> str:
        if self.suffix:
            return f"{self.product_prefix}_{self.suffix}"
        return self.product_prefix

    @property
    def filename(self) -> str:
        return f"{self.stem}{self.extension}"


def normalize_token(value: str) -> str:
    return " ".join(value.strip().split()).upper()


def split_suffix(stem: str) -> tuple[str, str]:
    """Split a filename stem into product prefix and suffix."""
    upper = stem.upper()

    for view in VIEW_TYPES:
        marker = f"_{view}"
        idx = upper.rfind(marker)
        if idx == -1:
            continue

        prefix = stem[:idx]
        suffix = stem[idx + 1 :]
        return prefix, suffix

    return stem, ""


def prefix_from_tds_filename(path: Path) -> str | None:
    """Extract product prefix from a TDS reference file name."""
    stem = path.stem
    upper = stem.upper()
    idx = upper.find(TDS_MARKER)
    if idx == -1:
        return None
    prefix = stem[:idx].rstrip("_")
    return prefix if prefix else None


def find_tds_prefix_in_folder(folder: Path) -> str | None:
    """Use TDS reference files in the folder as the authoritative product prefix."""
    counts: dict[str, int] = {}
    for path in folder.iterdir():
        if not path.is_file():
            continue
        if TDS_MARKER not in path.name.upper():
            continue
        prefix = prefix_from_tds_filename(path)
        if prefix:
            counts[prefix] = counts.get(prefix, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def strip_tds_artifact(prefix: str) -> str:
    upper = prefix.upper()
    if upper.endswith(TDS_MARKER):
        return prefix[: -len(TDS_MARKER)].rstrip("_")
    return prefix


def parse_image_suffix(stem: str) -> str:
    """Parse suffix from an image stem, handling mistaken `_TDS_` segments."""
    upper = stem.upper()
    tds_idx = upper.find(f"{TDS_MARKER}_")
    if tds_idx != -1:
        raw = stem[tds_idx + len(TDS_MARKER) + 1 :]
        return normalize_token(raw)

    _, suffix = split_suffix(stem)
    return normalize_token(suffix) if suffix else ""


def parse_filename(path: Path) -> ParsedFilename:
    stem = path.stem
    prefix, _ = split_suffix(stem)
    suffix = parse_image_suffix(stem)
    prefix = strip_tds_artifact(prefix)
    return ParsedFilename(
        product_prefix=prefix,
        suffix=suffix,
        extension=path.suffix,
    )


def resolve_folder_prefix(folder: Path, folder_files: list[Path] | None = None) -> str:
    """Pick canonical prefix; TDS reference files take priority."""
    tds_prefix = find_tds_prefix_in_folder(folder)
    if tds_prefix:
        return tds_prefix

    image_paths = [p for p in (folder_files or []) if p.suffix.lower() in IMAGE_EXTENSIONS]
    prefixes: dict[str, int] = {}

    for path in image_paths:
        parsed = parse_filename(path)
        candidate = strip_tds_artifact(parsed.product_prefix)
        if parsed.suffix and PRODUCT_PREFIX_RE.match(candidate.upper()):
            prefixes[candidate] = prefixes.get(candidate, 0) + 1

    if prefixes:
        return max(prefixes, key=prefixes.get)

    folder_name = folder.name
    match = PRODUCT_PREFIX_RE.search(folder_name.upper())
    if match:
        return match.group(0)

    return folder_name.split(" (")[0].strip()


def format_angle_suffix(view: str) -> str:
    """Canonical angle suffix for output filenames."""
    view = normalize_token(view)
    if view in ACTUAL_SIZE_LABELS:
        return "AS"
    if view in FRONT_BACK_LABELS:
        return "FRONT"
    if view in SIDE_VIEW_LABELS:
        return "SIDE"
    return view


def needs_tds_prefix(path: Path, folder_prefix: str) -> bool:
    parsed = parse_filename(path)
    current = normalize_token(strip_tds_artifact(parsed.product_prefix))
    target = normalize_token(folder_prefix)
    return current != target


def prefix_only_filename(folder_prefix: str, extension: str) -> str:
    return build_correct_filename(folder_prefix, "", extension)


def build_correct_filename(prefix: str, suffix: str, extension: str) -> str:
    suffix = normalize_token(suffix)
    view, color = parse_suffix_components(suffix)
    if view in ACTUAL_SIZE_LABELS and not color:
        suffix = "AS"
    elif view in FRONT_BACK_LABELS and not color:
        suffix = "FRONT"
    elif view in SIDE_VIEW_LABELS and not color:
        suffix = "SIDE"
    elif view in ANGLE_VIEWS and not color:
        suffix = format_angle_suffix(view)
    ext = extension if extension.startswith(".") else f".{extension}"
    if suffix:
        return f"{prefix}_{suffix}{ext}"
    return f"{prefix}{ext}"


def is_likely_misnamed(path: Path, folder_prefix: str) -> bool:
    parsed = parse_filename(path)
    if not parsed.suffix:
        return True
    if normalize_token(strip_tds_artifact(parsed.product_prefix)) != normalize_token(folder_prefix):
        return True
    if f"{TDS_MARKER}_" in path.stem.upper():
        return True
    expected = build_correct_filename(folder_prefix, parsed.suffix, parsed.extension)
    if path.name == expected or path.name.upper() == expected.upper():
        return False
    # ACTUAL SIZE / AS / FRONT / SIDE aliases
    if normalize_token(parsed.suffix) in ACTUAL_SIZE_LABELS | FRONT_BACK_LABELS | {"FRONT"} | SIDE_VIEW_LABELS:
        for alt_suffix in ("AS", "FRONT", "SIDE", "ACTUAL SIZE", "FRONT&BACK", "SIDE VIEW"):
            alt = build_correct_filename(folder_prefix, alt_suffix, parsed.extension)
            if path.name.upper() == alt.upper():
                return False
    return True


def parse_suffix_components(suffix: str) -> tuple[str, str]:
    """Split suffix label into view type and optional color."""
    suffix = normalize_token(suffix)
    if not suffix:
        return "", ""

    for view in VIEW_TYPES:
        if suffix == view:
            return view, ""
        marker = f"{view}_"
        if suffix.startswith(marker):
            return view, suffix[len(marker) :]

    parts = suffix.split("_", 1)
    if len(parts) == 2 and parts[0] in COLOR_VIEWS:
        return parts[0], parts[1]
    return suffix, ""


def compose_suffix(view: str, color: str = "") -> str:
    view = normalize_token(view)
    color = normalize_token(color)
    if view in COLOR_VIEWS and color:
        return f"{view}_{color}"
    return view


def suffix_kind(suffix: str) -> str:
    """Classify suffix as color matching (對色) or angle shot (角度)."""
    suffix = normalize_token(suffix)
    if not suffix:
        return "unknown"

    view, part = parse_suffix_components(suffix)
    if view in COLOR_VIEWS:
        if part and part not in ANGLE_VIEWS:
            return "color"
        if part in ANGLE_VIEWS:
            return "angle"
        return "color"
    if view in ANGLE_VIEWS:
        return "angle"
    return "angle"
