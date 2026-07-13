#!/usr/bin/env python3
"""Extract all file names from a OneDrive folder and export to CSV."""

import argparse
import csv
import os
from datetime import datetime
from pathlib import Path


def should_skip(path: Path) -> bool:
    name = path.name
    if name == "Icon\r" or name == ".DS_Store":
        return True
    if name.startswith("~$"):
        return True
    return False


def collect_files(root: Path) -> list[dict]:
    rows = []
    root = root.resolve()

    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            file_path = Path(dirpath) / filename
            if should_skip(file_path):
                continue

            stat = file_path.stat()
            rel_path = file_path.relative_to(root)
            parent = rel_path.parent
            parent_str = "" if str(parent) == "." else str(parent)

            rows.append(
                {
                    "file_name": filename,
                    "relative_path": str(rel_path),
                    "parent_folder": parent_str,
                    "extension": file_path.suffix.lower(),
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "full_path": str(file_path),
                }
            )

    rows.sort(key=lambda r: r["relative_path"].lower())
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract OneDrive folder file list to CSV."
    )
    parser.add_argument("folder", help="Path to the OneDrive folder")
    parser.add_argument(
        "-o",
        "--output",
        help="Output CSV path (default: <folder_name>_files.csv in cwd)",
    )
    args = parser.parse_args()

    root = Path(args.folder).expanduser()
    if not root.is_dir():
        raise SystemExit(f"Folder not found: {root}")

    rows = collect_files(root)
    output = Path(args.output) if args.output else Path(f"{root.name}_files.csv")

    fieldnames = [
        "file_name",
        "relative_path",
        "parent_folder",
        "extension",
        "size_bytes",
        "modified_at",
        "full_path",
    ]

    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {len(rows)} files to {output.resolve()}")


if __name__ == "__main__":
    main()
