from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from pvh_filename.filenames import normalize_token
from pvh_filename.runtime import is_frozen, portable_root

ARCHROMA_SHEET = "Archroma Color Master"
COLOR_MASTER_GLOBS = (
    "*Archroma*Color*Master*.xlsx",
    "*Archroma*Master*.xlsx",
    "*Color*Standard*Master*.xlsx",
)

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def sanitize_color_name(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("", name)
    return normalize_token(cleaned)


def clean_display_name(value: str) -> str:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    match = re.search(r"\(([^)]+)\)\s*$", text)
    if match and len(match.group(1)) >= 3:
        return match.group(1).strip()
    return text


def normalize_lookup_code(value: str) -> str:
    return re.sub(r"\D", "", str(value).strip())


def canonical_color_code(value: str) -> str:
    digits = normalize_lookup_code(value)
    if len(digits) != 6:
        return str(value).strip()
    if "-" in str(value) or " " in str(value):
        return f"{digits[:3]}-{digits[3:]}"
    return digits


class ColorMasterLookup:
    """Map Archroma color codes from OCR to European/US color names."""

    def __init__(self, by_code: dict[str, str], source: Path | None = None):
        self.by_code = by_code
        self.source = source

    @classmethod
    def from_excel(cls, path: Path) -> ColorMasterLookup:
        path = path.resolve()
        by_code: dict[str, str] = {}

        # Archroma sheet
        archroma = pd.read_excel(path, sheet_name=ARCHROMA_SHEET, header=1)
        for _, row in archroma.iterrows():
            raw_code = row.get("Archroma Code")
            if pd.isna(raw_code):
                continue
            code_key = normalize_lookup_code(str(raw_code))
            if not code_key:
                continue
            eu_name = clean_display_name(row.get("Color Name (歐洲色名)", ""))
            us_name = clean_display_name(row.get(" (美國色名)", ""))
            name = eu_name or us_name
            if name:
                by_code.setdefault(code_key, sanitize_color_name(name))

        # TCX sheet: codes like 19-1555TCX / 18-0937TCX
        try:
            tcx = pd.read_excel(path, sheet_name="TCX Color Master", header=0)
            for _, row in tcx.iterrows():
                raw_code = row.get("TCX")
                raw_name = row.get("Color Name (Customer)")
                if pd.isna(raw_code) or pd.isna(raw_name):
                    continue
                code_key = normalize_lookup_code(str(raw_code).replace("TCX", ""))
                if code_key:
                    by_code.setdefault(code_key, sanitize_color_name(str(raw_name)))
        except Exception:
            pass

        if not by_code:
            raise ValueError(f"No color codes found in {path}")

        return cls(by_code=by_code, source=path)

    def lookup_name(self, color_code: str) -> str | None:
        key = normalize_lookup_code(canonical_color_code(color_code))
        if not key:
            return None
        return self.by_code.get(key)

    def unique_names(self) -> list[str]:
        return sorted(set(self.by_code.values()))

    def fuzzy_lookup_name(self, raw_name: str, *, min_score: float = 0.78) -> str | None:
        """Match OCR / AI fragment to an official master color name."""
        needle = sanitize_color_name(raw_name)
        if not needle:
            return None
        names = self.unique_names()
        if needle in names:
            return needle

        needle_tokens = [t for t in needle.split("_") if t]
        compact_needle = needle.replace("_", "")

        # Unique whole-token matches, e.g. "DESERT SKY" tokens inside DESERT_SKY.
        token_hits = [
            name
            for name in names
            if needle_tokens and all(tok in name.split("_") for tok in needle_tokens)
        ]
        if len(token_hits) == 1:
            return token_hits[0]
        if len(token_hits) > 1 and len(needle_tokens) >= 2:
            # Prefer the shortest official name among multi-token hits.
            return sorted(token_hits, key=lambda n: (len(n), n))[0]

        best_name = ""
        best_score = 0.0
        for name in names:
            compact = name.replace("_", "")
            ratio = SequenceMatcher(None, needle, name).ratio()
            compact_ratio = SequenceMatcher(None, compact_needle, compact).ratio()
            score = max(ratio, compact_ratio)
            # Short fragments like "SKY" must not jump to "SKYWAY".
            if len(compact_needle) < 4:
                score = min(score, ratio)
            if score > best_score:
                best_score = score
                best_name = name
        if best_name and best_score >= min_score:
            return best_name
        return None

    def __len__(self) -> int:
        return len(self.by_code)


def find_color_master_in_folder(folder: Path) -> Path | None:
    folder = folder.resolve()
    for pattern in COLOR_MASTER_GLOBS:
        matches = sorted(folder.glob(pattern))
        if matches:
            return matches[0]
    return None


def default_color_master_path() -> Path | None:
    project_root = Path(__file__).resolve().parents[1]
    candidates = [
        project_root / "reference" / "Archroma_Color_Standard_Master_List_Shane.xlsx",
        project_root / "data" / "Archroma_Color_Standard_Master_List_Shane.xlsx",
        project_root / "models" / "Archroma_Color_Standard_Master_List_Shane.xlsx",
    ]
    if is_frozen():
        candidates.insert(
            0,
            portable_root() / "reference" / "Archroma_Color_Standard_Master_List_Shane.xlsx",
        )
    for path in candidates:
        if path.exists():
            return path
    return None


def resolve_color_master(
    folder: Path,
    explicit: Path | None = None,
) -> ColorMasterLookup | None:
    if explicit is not None:
        path = explicit.resolve()
        if not path.exists():
            raise FileNotFoundError(f"Color master not found: {path}")
        return ColorMasterLookup.from_excel(path)

    for path in (find_color_master_in_folder(folder), default_color_master_path()):
        if path and path.exists():
            return ColorMasterLookup.from_excel(path)
    return None
