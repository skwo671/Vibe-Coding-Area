#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from pvh_filename.predict import apply_renames, predict_renames, write_rename_report

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data/PVH EU"
DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models/suffix_classifier"
DEFAULT_REPORT = Path(__file__).resolve().parents[1] / "output/rename_report.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict and optionally apply corrected PVH image filenames.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--confidence", type=float, default=0.55)
    parser.add_argument("--apply", action="store_true", help="Actually rename files with high confidence")
    args = parser.parse_args()

    rows = predict_renames(args.data, args.model, confidence_threshold=args.confidence)
    write_rename_report(rows, args.report)

    rename_rows = [r for r in rows if r["action"] == "rename"]
    review_rows = [r for r in rows if r["action"] == "review"]
    print(f"Report: {args.report}")
    print(f"Suggested renames: {len(rename_rows)}")
    print(f"Needs manual review: {len(review_rows)}")

    if args.apply:
        applied = apply_renames(rows, dry_run=False)
        renamed = sum(1 for r in applied if r.get("status") == "renamed")
        print(f"Renamed files: {renamed}")
    else:
        print("Dry run only. Re-run with --apply to rename files.")


if __name__ == "__main__":
    main()
