"""Learned color-name memory from user-corrected filenames.

Learn mode stores color samples (e.g. xxx_D65_DESERT_SKY.jpg). Work mode can:
1. Map OCR color codes → learned official names
2. Match visually similar color cards via CLIP (kNN)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from pvh_filename.color_master import normalize_lookup_code, sanitize_color_name
from pvh_filename.model import ClipEmbedder
from pvh_filename.simple_labels import COLOR_LIGHTS, normalize_token
from pvh_filename.simple_ocr import ARCHROMA_CODE_RE, detect_color_card

MEMORY_FILENAME = "color_name_memory.joblib"
MEMORY_JSON = "color_name_memory.json"


@dataclass(frozen=True)
class ColorMemoryHit:
    suffix: str
    light: str
    name: str
    code: str
    source: str  # learned_code | learned_visual
    score: float = 1.0


def default_color_memory_path(model_dir: Path) -> Path:
    return model_dir / MEMORY_FILENAME


def split_color_suffix(suffix: str) -> tuple[str, str, str]:
    """
    Parse CWF_DESERT_SKY / D65_654-920 → (light, name, code).
    """
    text = normalize_token(suffix)
    light = "D65"
    rest = text
    for cand in sorted(COLOR_LIGHTS, key=len, reverse=True):
        if text == cand:
            return cand, "", ""
        prefix = f"{cand}_"
        if text.startswith(prefix):
            light = cand
            rest = text[len(prefix) :].strip("_ ")
            break

    code = ""
    name = ""
    match = ARCHROMA_CODE_RE.search(rest.replace("_", "-"))
    if match:
        code = f"{match.group(1)}-{match.group(2)}"
        # Name may appear before the code in the suffix.
        before = rest[: match.start()].strip(" _-")
        name = sanitize_color_name(before.replace("-", " ")) if before else ""
    else:
        digits = re.sub(r"\D", "", rest)
        if len(digits) == 6 and re.fullmatch(r"[\d\-_ ]+", rest.replace(" ", "")):
            code = f"{digits[:3]}-{digits[3:]}"
        else:
            name = sanitize_color_name(rest.replace("-", " "))
    return light, name, code


class ColorNameMemory:
    """Code overrides + visual neighbors for color rename."""

    def __init__(
        self,
        *,
        by_code: dict[str, dict] | None = None,
        entries: list[dict] | None = None,
        embeddings: np.ndarray | None = None,
        source: Path | None = None,
    ) -> None:
        self.by_code = by_code or {}
        self.entries = entries or []
        self.embeddings = embeddings
        self.source = source

    def __len__(self) -> int:
        return len(self.entries)

    def lookup_by_code(self, color_code: str) -> ColorMemoryHit | None:
        key = normalize_lookup_code(color_code)
        if not key:
            return None
        row = self.by_code.get(key)
        if not row:
            return None
        return ColorMemoryHit(
            suffix=str(row.get("suffix") or ""),
            light=str(row.get("light") or "D65"),
            name=str(row.get("name") or ""),
            code=str(row.get("code") or color_code),
            source="learned_code",
            score=1.0,
        )

    def lookup_by_embedding(
        self,
        embedding: np.ndarray,
        *,
        min_similarity: float = 0.86,
    ) -> ColorMemoryHit | None:
        if self.embeddings is None or not len(self.entries):
            return None
        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        bank = np.asarray(self.embeddings, dtype=np.float32)
        if bank.ndim != 2 or bank.shape[0] != len(self.entries):
            return None
        # Cosine similarity
        denom = (np.linalg.norm(bank, axis=1) * (np.linalg.norm(vec) + 1e-8)) + 1e-8
        sims = (bank @ vec) / denom
        idx = int(np.argmax(sims))
        score = float(sims[idx])
        if score < min_similarity:
            return None
        row = self.entries[idx]
        return ColorMemoryHit(
            suffix=str(row.get("suffix") or ""),
            light=str(row.get("light") or "D65"),
            name=str(row.get("name") or ""),
            code=str(row.get("code") or ""),
            source="learned_visual",
            score=score,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "by_code": self.by_code,
                "entries": self.entries,
                "embeddings": self.embeddings,
            },
            path,
        )
        # Human-readable summary next to joblib.
        summary = {
            "num_entries": len(self.entries),
            "num_codes": len(self.by_code),
            "by_code": {
                code: {
                    "name": row.get("name"),
                    "light": row.get("light"),
                    "suffix": row.get("suffix"),
                }
                for code, row in sorted(self.by_code.items())
            },
            "names": sorted(
                {
                    str(e.get("name"))
                    for e in self.entries
                    if e.get("name")
                }
            ),
        }
        (path.parent / MEMORY_JSON).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "ColorNameMemory | None":
        if not path.exists():
            return None
        try:
            payload = joblib.load(path)
        except Exception:
            return None
        return cls(
            by_code=dict(payload.get("by_code") or {}),
            entries=list(payload.get("entries") or []),
            embeddings=payload.get("embeddings"),
            source=path,
        )


def _ocr_code_for_learn(path: Path) -> str:
    try:
        ocr = detect_color_card(path)
    except Exception:
        return ""
    return ocr.color_code if ocr else ""


def rebuild_color_memory(
    model_dir: Path,
    color_rows: list[dict],
    *,
    run_ocr: bool = True,
    build_embeddings: bool = True,
) -> ColorNameMemory:
    """
    Rebuild memory from learn-bank color rows.

    Each row needs: image_path, suffix (e.g. D65_DESERT_SKY)
    """
    by_code: dict[str, dict] = {}
    entries: list[dict] = []

    for row in color_rows:
        suffix = str(row.get("suffix") or "")
        image_path = str(row.get("image_path") or "")
        if not suffix or not image_path or not Path(image_path).exists():
            continue
        light, name, code = split_color_suffix(suffix)
        if run_ocr and not code:
            code = _ocr_code_for_learn(Path(image_path))
        entry = {
            "image_path": image_path,
            "suffix": f"{light}_{name}" if name else (f"{light}_{code}" if code else suffix),
            "light": light,
            "name": name,
            "code": code,
            "source_name": row.get("source_name", ""),
        }
        entries.append(entry)
        if code:
            key = normalize_lookup_code(code)
            # Prefer entries that include an explicit color name.
            prev = by_code.get(key)
            if prev is None or (name and not prev.get("name")):
                by_code[key] = {
                    "code": code,
                    "name": name,
                    "light": light,
                    "suffix": entry["suffix"],
                }

    embeddings = None
    if build_embeddings and entries:
        embedder = ClipEmbedder()
        paths = [e["image_path"] for e in entries]
        emb, valid = embedder.encode_paths(paths)
        if len(valid) == len(paths):
            embeddings = emb
            # Keep entries order aligned with embeddings.
        elif valid:
            # Filter to successfully embedded paths.
            valid_set = set(valid)
            keep = [e for e in entries if e["image_path"] in valid_set]
            order = {p: i for i, p in enumerate(valid)}
            keep.sort(key=lambda e: order[e["image_path"]])
            entries = keep
            embeddings = emb

    memory = ColorNameMemory(by_code=by_code, entries=entries, embeddings=embeddings)
    memory.save(default_color_memory_path(model_dir))
    return memory
