from __future__ import annotations

import csv
from pathlib import Path

from pvh_filename.actual_size import has_duplicate_pattern
from pvh_filename.color_master import ColorMasterLookup, resolve_color_master
from pvh_filename.dataset import build_records, records_to_dataframe, iter_image_paths
from pvh_filename.filenames import build_correct_filename, format_angle_suffix, parse_suffix_components
from pvh_filename.model import ClipEmbedder, HierarchicalClassifier, default_model_path
from pvh_filename.ocr import extract_color_code, tesseract_status_message


def load_classifier(model_dir: Path) -> HierarchicalClassifier:
    return HierarchicalClassifier.load(default_model_path(model_dir))


def predict_renames(
    data_root: Path,
    model_dir: Path,
    confidence_threshold: float = 0.55,
    only_misnamed: bool = False,
    color_master: ColorMasterLookup | None = None,
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
        color_name = ""
        suffix_source = "model"
        skip_reason = ""
        if predicted_kind == "color":
            color_code = extract_color_code(record.path) or ""
            if color_code:
                light_source, _ = parse_suffix_components(predicted_suffix)
                if light_source not in {"CWF", "D65"}:
                    light_source = "CWF"
                if color_master:
                    color_name = color_master.lookup_name(color_code) or ""
                if color_name and light_source:
                    predicted_suffix = f"{light_source}_{color_name}"
                    suffix_source = "ocr+color_master"
                elif color_code and light_source:
                    predicted_suffix = f"{light_source}_{color_code}"
                    suffix_source = "ocr_color_code"
                    if color_master:
                        skip_reason = f"色號 {color_code} 唔喺對照表，暫用色號改名"
                else:
                    predicted_suffix = ""
                    suffix_source = "ocr_not_found"
                    skip_reason = "讀到色號但未能組合檔名"
            else:
                predicted_suffix = ""
                suffix_source = "ocr_not_found"
                skip_reason = "OCR 讀唔到色號（請確認 Tesseract 已安裝，色卡數字清晰）"
        elif predicted_kind == "angle":
            if has_duplicate_pattern(record.path):
                predicted_suffix = "AS"
                suffix_source = "duplicate_pattern"
            else:
                predicted_suffix = format_angle_suffix(predicted_suffix)
                if predicted_suffix == "AS":
                    suffix_source = "model_actual_size"

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
            if action == "review" and not skip_reason:
                skip_reason = f"信心度太低 ({confidence:.2f})"

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
                "color_name": color_name,
                "suffix_source": suffix_source,
                "predicted_suffix": predicted_suffix,
                "proposed_name": proposed_name,
                "confidence": round(confidence, 4),
                "action": action,
                "skip_reason": skip_reason,
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
        "color_name",
        "suffix_source",
        "predicted_suffix",
        "proposed_name",
        "confidence",
        "action",
        "skip_reason",
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


def print_rename_summary(summary: dict, rows: list[dict]) -> None:
    print("=" * 50)
    print(f"圖片總數:     {summary.get('total_images', 0)}")
    print(f"建議改名:     {summary.get('suggestions', 0)}")
    print(f"實際改名:     {summary.get('renamed', 0)}")
    print(f"需要檢查:     {summary.get('needs_review', 0)}")
    if summary.get("color_master"):
        print(f"色號對照表: {summary['color_master']}")
    print(tesseract_status_message())
    print("=" * 50)

    if summary.get("renamed", 0) == 0 and rows:
        print("\n未改名原因：")
        reasons: dict[str, int] = {}
        for row in rows:
            if row.get("action") == "rename":
                continue
            reason = row.get("skip_reason") or row.get("suffix_source") or "未知"
            reasons[reason] = reasons.get(reason, 0) + 1
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  - {reason}: {count} 張")

        print("\n首 5 張待檢查：")
        shown = 0
        for row in rows:
            if row.get("action") != "rename":
                print(
                    f"  {row.get('current_name')} -> {row.get('predicted_kind')} / "
                    f"{row.get('suffix_source')} / {row.get('skip_reason') or '-'}"
                )
                shown += 1
                if shown >= 5:
                    break
    print()


def rename_folder(
    folder: Path,
    model_dir: Path,
    *,
    apply: bool = False,
    confidence: float = 0.55,
    report_path: Path | None = None,
    write_report: bool = True,
    color_master_path: Path | None = None,
) -> dict:
    folder = folder.resolve()
    report_path = report_path or (folder / "rename_report.csv")
    color_master = resolve_color_master(folder, color_master_path)
    total_images = len(list(iter_image_paths(folder)))

    if total_images == 0:
        summary = {
            "folder": str(folder),
            "report": None,
            "total_images": 0,
            "suggestions": 0,
            "auto_rename": 0,
            "needs_review": 0,
            "renamed": 0,
            "error": "資料夾內搵唔到圖片。請將圖片放入「待改名圖片」資料夾。",
        }
        print_rename_summary(summary, [])
        print("提示: 確認圖片係 .jpg/.jpeg/.png，而且唔好放喺 app/ 或 models/ 入面。")
        return summary

    rows = predict_renames(
        folder,
        model_dir,
        confidence_threshold=confidence,
        color_master=color_master,
    )
    if write_report:
        write_rename_report(rows, report_path)

    rename_rows = [r for r in rows if r["action"] == "rename"]
    review_rows = [r for r in rows if r["action"] == "review"]
    applied: list[dict] = []

    if apply and rename_rows:
        applied = apply_renames(rows, dry_run=False)

    summary = {
        "folder": str(folder),
        "report": str(report_path) if write_report else None,
        "color_master": str(color_master.source) if color_master else None,
        "color_master_entries": len(color_master) if color_master else 0,
        "tesseract": tesseract_status_message(),
        "total_images": total_images,
        "suggestions": len(rows),
        "auto_rename": len(rename_rows),
        "needs_review": len(review_rows),
        "renamed": sum(1 for r in applied if r.get("status") == "renamed"),
    }
    print_rename_summary(summary, rows)
    return summary
