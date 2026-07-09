from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pvh_filename.filenames import (
    IMAGE_EXTENSIONS,
    build_correct_filename,
    find_tds_prefix_in_folder,
    is_likely_misnamed,
    parse_filename,
    parse_image_suffix,
    resolve_folder_prefix,
    suffix_kind,
)


@dataclass(frozen=True)
class ImageRecord:
    path: Path
    folder: Path
    folder_prefix: str
    prefix_source: str
    suffix: str
    suffix_kind: str
    extension: str
    current_name: str
    expected_name: str
    is_misnamed: bool


def iter_image_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            if path.name.startswith("~$") or path.name == ".DS_Store":
                continue
            paths.append(path)
    return sorted(paths)


def build_records(root: Path) -> list[ImageRecord]:
    root = root.resolve()
    images = iter_image_paths(root)
    by_folder: dict[Path, list[Path]] = {}
    for path in images:
        by_folder.setdefault(path.parent, []).append(path)

    records: list[ImageRecord] = []
    for folder, folder_images in by_folder.items():
        folder_prefix = resolve_folder_prefix(folder, folder_images)
        prefix_source = "tds" if find_tds_prefix_in_folder(folder) else "inferred"
        for path in folder_images:
            suffix = parse_image_suffix(path.stem)
            expected = build_correct_filename(folder_prefix, suffix, path.suffix)
            records.append(
                ImageRecord(
                    path=path,
                    folder=folder,
                    folder_prefix=folder_prefix,
                    prefix_source=prefix_source,
                    suffix=suffix,
                    suffix_kind=suffix_kind(suffix),
                    extension=path.suffix,
                    current_name=path.name,
                    expected_name=expected,
                    is_misnamed=is_likely_misnamed(path, folder_prefix),
                )
            )
    return records


def records_to_dataframe(records: list[ImageRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "path": str(r.path),
                "folder": str(r.folder),
                "folder_prefix": r.folder_prefix,
                "prefix_source": r.prefix_source,
                "suffix": r.suffix,
                "suffix_kind": r.suffix_kind,
                "extension": r.extension,
                "current_name": r.current_name,
                "expected_name": r.expected_name,
                "is_misnamed": r.is_misnamed,
            }
            for r in records
        ]
    )
