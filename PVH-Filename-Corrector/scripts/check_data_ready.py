#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from pvh_filename.dataset import iter_image_paths

DEFAULT_LOCAL = Path(__file__).resolve().parents[1] / "data/PVH EU"
DEFAULT_ONEDRIVE = (
    Path.home() / "Library/CloudStorage/OneDrive-MingoTrimsInternationalLimited/PVH EU"
)


def count_readable(paths: list[Path]) -> tuple[int, int]:
    readable = 0
    failed = 0
    for path in paths:
        try:
            with path.open("rb") as f:
                f.read(1024)
            readable += 1
        except OSError:
            failed += 1
    return readable, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether PVH EU local copy is ready for training.")
    parser.add_argument("--local", type=Path, default=DEFAULT_LOCAL)
    parser.add_argument("--source", type=Path, default=DEFAULT_ONEDRIVE)
    args = parser.parse_args()

    source_images = iter_image_paths(args.source)
    local_images = iter_image_paths(args.local) if args.local.exists() else []

    local_readable, local_failed = count_readable(local_images)
    source_readable, source_failed = count_readable(source_images)

    print(f"OneDrive images: {len(source_images)} total, {source_readable} readable, {source_failed} unavailable")
    print(f"Local images:    {len(local_images)} total, {local_readable} readable, {local_failed} unavailable")

    if local_readable >= len(source_images) * 0.95:
        print("Status: READY for training on local copy.")
    elif local_readable > 0:
        print("Status: PARTIAL copy. Continue copy_from_onedrive.py before training.")
    else:
        print("Status: NOT READY. Pin PVH EU in OneDrive, then run copy_from_onedrive.py.")


if __name__ == "__main__":
    main()
