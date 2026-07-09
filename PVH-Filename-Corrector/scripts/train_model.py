#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pvh_filename.model import train_suffix_model
from pvh_filename.predict import export_dataset_manifest

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data/PVH EU"
DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models/suffix_classifier"
DEFAULT_ONEDRIVE = (
    Path.home() / "Library/CloudStorage/OneDrive-MingoTrimsInternationalLimited/PVH EU"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train CLIP-based suffix classifier for PVH image filenames.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Local PVH EU copy (run copy_from_onedrive.py first)")
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--min-samples", type=int, default=2)
    parser.add_argument("--manifest", type=Path, default=None, help="Optional CSV manifest output path")
    parser.add_argument(
        "--from-onedrive",
        action="store_true",
        help=f"Train directly from OneDrive path ({DEFAULT_ONEDRIVE})",
    )
    args = parser.parse_args()

    data_root = DEFAULT_ONEDRIVE if args.from_onedrive else args.data
    if not data_root.is_dir():
        raise SystemExit(
            f"Data folder not found: {data_root}\n"
            "Tip: In OneDrive, right-click 'PVH EU' -> Always keep on this device,\n"
            "then run: python scripts/copy_from_onedrive.py"
        )

    if args.manifest:
        export_dataset_manifest(data_root, args.manifest)
        print(f"Manifest exported to {args.manifest}")

    metrics = train_suffix_model(data_root, args.output, min_samples_per_class=args.min_samples)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
