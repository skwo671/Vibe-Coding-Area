from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import numpy as np

from pvh_filename.color_master import resolve_color_master
from pvh_filename.model import ClipEmbedder, HierarchicalClassifier, default_model_path
from pvh_filename.simple_angle_heuristics import looks_like_corner, looks_like_side_view
from pvh_filename.simple_as import has_two_similar_products
from pvh_filename.simple_labels import (
    ANGLE_ALIAS,
    ANGLE_LABELS,
    build_filename,
    find_tds_prefix,
    iter_image_paths,
    normalize_token,
)
from pvh_filename.simple_model import (
    SimpleKindClassifier,
    default_angle_model_path,
    default_simple_model_path,
)
from pvh_filename.simple_ocr import detect_color_card_code, tesseract_status_message


def _unique_name(folder: Path, filename: str, taken: set[str]) -> str:
    target = folder / filename
    if filename not in taken and not target.exists():
        taken.add(filename)
        return filename
    stem = Path(filename).stem
    ext = Path(filename).suffix
    n = 2
    while True:
        candidate = f"{stem}_{n}{ext}"
        if candidate not in taken and not (folder / candidate).exists():
            taken.add(candidate)
            return candidate
        n += 1


def _map_legacy_angle(suffix: str) -> str:
    return ANGLE_ALIAS.get(normalize_token(suffix), "FRONT")


def _resolve_angle_suffix(
    path: Path,
    embedding: np.ndarray | None,
    angle_clf: SimpleKindClassifier | None,
    legacy: HierarchicalClassifier | None,
) -> tuple[str, str]:
    """Pick AS / FRONT / SIDE / CORNER for an angle shot."""
    if has_two_similar_products(path):
        return "AS", "duplicate_pattern"

    if angle_clf is not None and embedding is not None:
        labels, confs = angle_clf.predict_kind(embedding.reshape(1, -1))
        label = normalize_token(labels[0])
        if label in ANGLE_LABELS and confs[0] >= 0.35:
            return label, "angle_model"

    if legacy is not None and embedding is not None:
        suffixes, kinds, confs = legacy.predict(embedding.reshape(1, -1))
        if kinds and kinds[0] == "angle":
            mapped = _map_legacy_angle(suffixes[0])
            if mapped in ANGLE_LABELS:
                return mapped, "legacy_angle_model"

    if looks_like_side_view(path):
        return "SIDE", "heuristic_side"
    if looks_like_corner(path):
        return "CORNER", "heuristic_corner"
    return "FRONT", "single_product"


def predict_work_folder(
    folder: Path,
    model_dir: Path,
    *,
    apply: bool = True,
    write_report: bool = True,
) -> dict:
    folder = folder.resolve()
    images = iter_image_paths(folder)
    prefix = find_tds_prefix(folder) or folder.name
    color_master = resolve_color_master(folder)

    kind_path = default_simple_model_path(model_dir)
    angle_path = default_angle_model_path(model_dir)
    kind_clf = SimpleKindClassifier.load(kind_path) if kind_path.exists() else None
    angle_clf = SimpleKindClassifier.load(angle_path) if angle_path.exists() else None

    legacy = None
    legacy_file = default_model_path(model_dir)
    if legacy_file.exists():
        try:
            legacy = HierarchicalClassifier.load(legacy_file)
        except Exception:
            legacy = None

    kinds = ["angle"] * len(images)
    kind_confs = [0.0] * len(images)
    emb_map: dict[str, np.ndarray] = {}

    if images and (kind_clf or angle_clf or legacy):
        embedder = ClipEmbedder()
        embeddings, valid_paths = embedder.encode_paths([str(p) for p in images])
        emb_map = {p: embeddings[i] for i, p in enumerate(valid_paths)}
        if kind_clf:
            valid_idx = [i for i, path in enumerate(images) if str(path) in emb_map]
            if valid_idx:
                sub = np.vstack([emb_map[str(images[i])] for i in valid_idx])
                pred_labels, pred_conf = kind_clf.predict_kind(sub)
                for j, i in enumerate(valid_idx):
                    kinds[i] = pred_labels[j]
                    kind_confs[i] = pred_conf[j]

    rows: list[dict] = []
    taken: set[str] = set()

    for path, kind, conf in zip(images, kinds, kind_confs, strict=True):
        color_code = detect_color_card_code(path) or ""
        suffix = ""
        source = "model"
        reason = ""
        final_kind = kind
        embedding = emb_map.get(str(path))

        if color_code:
            final_kind = "color"
            color_name = color_master.lookup_name(color_code) if color_master else ""
            if color_name:
                suffix = f"CWF_{color_name}"
                source = "ocr+color_master"
            else:
                suffix = f"CWF_{color_code}"
                source = "ocr_color_code"
        elif kind == "color":
            final_kind = "color"
            source = "model_color_no_ocr"
            reason = "模型判斷為對色相，但 OCR 讀唔到色號"
        else:
            final_kind = "angle"
            suffix, source = _resolve_angle_suffix(path, embedding, angle_clf, legacy)

        proposed = ""
        action = "review"
        if suffix:
            proposed = _unique_name(folder, build_filename(prefix, suffix, path.suffix), taken)
            if normalize_token(path.name) == normalize_token(proposed):
                action = "skip_same"
                taken.discard(proposed)
                proposed = path.name
            else:
                action = "rename"
        else:
            prefix_name = _unique_name(folder, build_filename(prefix, "", path.suffix), taken)
            if normalize_token(path.stem) != normalize_token(prefix):
                proposed = prefix_name
                action = "rename"
                source = "prefix_only"
                reason = reason or "未能判斷後綴，僅加 TDS 前綴"
            else:
                taken.discard(prefix_name)
                reason = reason or "無需改名"
                action = "skip"

        rows.append(
            {
                "current_name": path.name,
                "path": str(path),
                "folder_prefix": prefix,
                "predicted_kind": final_kind,
                "color_code": color_code,
                "suffix": suffix,
                "suffix_source": source,
                "proposed_name": proposed,
                "confidence": round(float(conf), 4),
                "action": action,
                "skip_reason": reason,
            }
        )

    renamed = 0
    if apply:
        for row in rows:
            if row["action"] != "rename" or not row["proposed_name"]:
                continue
            src = Path(row["path"])
            dst = src.with_name(row["proposed_name"])
            if src.resolve() == dst.resolve():
                continue
            src.rename(dst)
            row["status"] = "renamed"
            renamed += 1

    report_path = folder / "rename_report.csv"
    if write_report:
        fields = [
            "current_name",
            "folder_prefix",
            "predicted_kind",
            "color_code",
            "suffix",
            "suffix_source",
            "proposed_name",
            "confidence",
            "action",
            "skip_reason",
        ]
        with report_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fields})

    summary = {
        "mode": "work",
        "folder": str(folder),
        "prefix": prefix,
        "tesseract": tesseract_status_message(),
        "model": str(kind_path) if kind_path.exists() else None,
        "angle_model": str(angle_path) if angle_path.exists() else None,
        "total_images": len(images),
        "renamed": renamed,
        "report": str(report_path) if write_report else None,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    print("=" * 50)
    print("模式:       工作模式（自動改名）")
    print(f"圖片總數:   {summary['total_images']}")
    print(f"實際改名:   {summary['renamed']}")
    print(f"TDS 前綴:   {summary['prefix']}")
    print("角度相:     AS / FRONT / SIDE / CORNER")
    print(summary["tesseract"])
    print("=" * 50)
    for row in rows[:8]:
        print(
            f"  {row['current_name']} -> {row.get('proposed_name') or '-'} "
            f"[{row['predicted_kind']}/{row['suffix'] or '-'}/{row['suffix_source']}]"
        )
    if len(rows) > 8:
        print(f"  ... 其餘 {len(rows) - 8} 張見 rename_report.csv")
    print()
    return summary
