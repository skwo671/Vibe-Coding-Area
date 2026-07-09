from __future__ import annotations

import csv
from pathlib import Path

from pvh_filename.dataset import build_records, records_to_dataframe, iter_image_paths
from pvh_filename.filenames import build_correct_filename, parse_suffix_components
from pvh_filename.model import ClipEmbedder, HierarchicalClassifier, default_model_path
from pvh_filename.ocr import extract_color_code


def load_classifier(model_dir: Path) -> HierarchicalClassifier:
    return HierarchicalClassifier.load(default_model_path(model_dir))


def predict_renames(
    data_root: Path,
    model_dir: Path,
    confidence_threshold: float = 0.55,
    only_misnamed: bool = False,
) -> list[dict]:
    records = build_records(data_root)
    if only_misnamed:
        image_records = [r for r in records if r.is_misnamed]
    else:
        image_records = [r for r in records if r.suffix or r.is_misnamed]
    if not image_records:
        return []

    paths = [str(r.path) for r in image_records]
    embedder = ClipEmbedder()
    embeddings, valid_paths = embedder.encode_paths(paths)
    valid_set = set(valid_paths)
    valid_records = [r for r in image_records if str(r.path) in valid_set]
    classifier = load_classifier(model_dir)
    predicted_suffixes, predicted_kinds, confidences = classifier.predict(embeddings)

    results: list[dict] = []
    for record, predicted_suffix, predicted_kind, confidence in zip(
        valid_records, predicted_suffixes, predicted_kinds, confidences, strict=True
    ):
        color_code = ""
        suffix_source = "model"
        if predicted_kind == "color":
            color_code = extract_color_code(record.path) or ""
            if color_code:
                light_source, _ = parse_suffix_components(predicted_suffix)
                if light_source not in {"CWF", "D65"}:
                    light_source = ""
                predicted_suffix = f"{light_source}_{color_code}" if light_source else ""
                suffix_source = "ocr_color_code"
            else:
                predicted_suffix = ""
                suffix_source = "ocr_not_found"

        view, color = parse_suffix_components(predicted_suffix)
        proposed_name = ""
        if predicted_suffix:
            proposed_name = build_correct_filename(
                record.folder_prefix,
                predicted_suffix,
                record.extension,
            )
            if record.current_name == proposed_name or record.current_name.upper() == proposed_name.upper():
                continue

        if predicted_kind == "color" and not color_code:
            action = "review"
        else:
            action = "rename" if confidence >= confidence_threshold else "review"

        results.append(
            {
                "path": str(record.path),
                "folder_prefix": record.folder_prefix,
                "prefix_source": record.prefix_source,
                "current_name": record.current_name,
                "predicted_kind": predicted_kind,
                "predicted_view": view,
                "predicted_color": color,
                "color_code": color_code,
                "suffix_source": suffix_source,
                "predicted_suffix": predicted_suffix,
                "proposed_name": proposed_name,
                "confidence": round(confidence, 4),
                "action": action,
            }
        )
    return results


def write_rename_report(rows: list[dict], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "path",
        "folder_prefix",
        "prefix_source",
        "current_name",
        "predicted_kind",
        "predicted_view",
        "predicted_color",
        "color_code",
        "suffix_source",
        "predicted_suffix",
        "proposed_name",
        "confidence",
        "action",
    ]
    with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def apply_renames(rows: list[dict], dry_run: bool = True) -> list[dict]:
    applied: list[dict] = []
    for row in rows:
        if row["action"] != "rename":
            continue
        src = Path(row["path"])
        dst = src.with_name(row["proposed_name"])
        if src.name == dst.name:
            continue
        if dst.exists():
            row = {**row, "status": "skipped_exists"}
            applied.append(row)
            continue
        if not dry_run:
            src.rename(dst)
            row = {**row, "status": "renamed", "new_path": str(dst)}
        else:
            row = {**row, "status": "dry_run"}
        applied.append(row)
    return applied


def export_dataset_manifest(data_root: Path, output_csv: Path) -> None:
    records = build_records(data_root)
    df = records_to_dataframe(records)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")


def rename_folder(
    folder: Path,
    model_dir: Path,
    *,
    apply: bool = False,
    confidence: float = 0.55,
    report_path: Path | None = None,
    write_report: bool = True,
) -> dict:
    folder = folder.resolve()
    report_path = report_path or (folder / "rename_report.csv")

    rows = predict_renames(folder, model_dir, confidence_threshold=confidence)
    if write_report:
        write_rename_report(rows, report_path)

    rename_rows = [r for r in rows if r["action"] == "rename"]
    review_rows = [r for r in rows if r["action"] == "review"]
    applied: list[dict] = []

    if apply and rename_rows:
        applied = apply_renames(rows, dry_run=False)

    return {
        "folder": str(folder),
        "report": str(report_path) if write_report else None,
        "total_images": len(list(iter_image_paths(folder))),
        "suggestions": len(rows),
        "auto_rename": len(rename_rows),
        "needs_review": len(review_rows),
        "renamed": sum(1 for r in applied if r.get("status") == "renamed"),
    }
