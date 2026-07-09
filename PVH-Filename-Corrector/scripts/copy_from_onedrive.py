#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

DEFAULT_SOURCE = Path.home() / "Library/CloudStorage/OneDrive-MingoTrimsInternationalLimited/PVH EU"
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "data/PVH EU"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


def should_copy(path: Path, images_only: bool) -> bool:
    if path.name.startswith("~$") or path.name == ".DS_Store":
        return False
    if images_only:
        return path.suffix.lower() in IMAGE_EXTENSIONS
    return True


def hydrate_and_copy(src: Path, dest: Path, retries: int = 3, wait_seconds: float = 2.0) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == src.stat().st_size and dest.stat().st_size > 0:
        return True

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with src.open("rb") as f:
                f.read(1024)
            shutil.copy2(src, dest)
            return True
        except Exception as exc:  # noqa: BLE001 - keep copy resilient for cloud files
            last_error = exc
            time.sleep(wait_seconds * attempt)
    print(f"FAILED ({last_error}): {src}")
    return False


def copy_pvh_eu(source: Path, dest: Path, images_only: bool = True) -> dict:
    if not source.is_dir():
        raise SystemExit(f"Source folder not found: {source}")

    copied = 0
    skipped = 0
    failed = 0
    total = 0

    for src in sorted(source.rglob("*")):
        if not src.is_file() or not should_copy(src, images_only):
            continue
        total += 1
        rel = src.relative_to(source)
        dst = dest / rel
        if dst.exists() and dst.stat().st_size > 0 and dst.stat().st_size == src.stat().st_size:
            skipped += 1
            continue
        if hydrate_and_copy(src, dst):
            copied += 1
            if copied % 100 == 0:
                print(f"Copied {copied} files...")
        else:
            failed += 1

    summary = {"total": total, "copied": copied, "skipped": skipped, "failed": failed, "dest": str(dest)}
    print(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy PVH EU from OneDrive with hydration retries.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--all-files", action="store_true", help="Copy all files, not just images")
    args = parser.parse_args()
    copy_pvh_eu(args.source, args.dest, images_only=not args.all_files)


if __name__ == "__main__":
    main()
