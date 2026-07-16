from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from pvh_filename.simple_labels import ANGLE_LABELS, iter_image_paths, parse_simple_label
from pvh_filename.simple_color_memory import rebuild_color_memory
from pvh_filename.simple_model import (
    default_angle_model_path,
    default_simple_model_path,
    train_simple_angle_model,
    train_simple_kind_model,
)


def learn_bank_dir(model_dir: Path) -> Path:
    return model_dir / "learn_bank"


def manifest_path(model_dir: Path) -> Path:
    return learn_bank_dir(model_dir) / "manifest.jsonl"


def load_manifest(model_dir: Path) -> list[dict]:
    path = manifest_path(model_dir)
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_manifest(model_dir: Path, rows: list[dict]) -> None:
    path = manifest_path(model_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def collect_labels_from_folder(folder: Path) -> list[dict]:
    samples: list[dict] = []
    for path in iter_image_paths(folder):
        label = parse_simple_label(path.stem)
        if not label:
            continue
        samples.append(
            {
                "path": str(path.resolve()),
                "kind": label.kind,
                "suffix": label.suffix,
                "filename": path.name,
            }
        )
    return samples


KEEP_IN_LEARN_FOLDER = {"請將已改正確檔名嘅圖片放喺呢度.txt"}


def cleanup_learn_folder(folder: Path, learned_paths: list[Path]) -> dict:
    """Delete learned samples (and leftover media) from the learn input folder."""
    deleted = 0
    failed = 0

    # First delete all successfully ingested images.
    for path in learned_paths:
        try:
            if path.exists() and path.is_file() and path.parent.resolve() == folder.resolve():
                path.unlink()
                deleted += 1
        except OSError:
            failed += 1

    # Also clear any remaining files except guide text.
    for path in folder.iterdir():
        if not path.is_file():
            continue
        if path.name in KEEP_IN_LEARN_FOLDER or path.suffix.lower() == ".txt":
            continue
        try:
            path.unlink()
            deleted += 1
        except OSError:
            failed += 1

    return {"deleted": deleted, "failed": failed}


def learn_from_folder(folder: Path, model_dir: Path, *, copy_images: bool = True) -> dict:
    """
    Learning mode:
    1. Scan folder for correctly named images.
    2. Save into learn_bank.
    3. Retrain kind model (angle vs color) and angle model (AS/FRONT/SIDE/CORNER).
    4. Rebuild color-name memory from corrected color filenames.
    5. Delete files/images from the learning folder after learning.
    """
    folder = folder.resolve()
    model_dir = model_dir.resolve()
    bank = learn_bank_dir(model_dir)
    images_dir = bank / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    collected = collect_labels_from_folder(folder)
    if not collected:
        print("學習模式：資料夾內搵唔到已正確命名嘅圖片。")
        print("請先手動改好檔名，例如：")
        print("  xxx_AS.jpg")
        print("  xxx_FRONT.jpg")
        print("  xxx_SIDE.jpg")
        print("  xxx_CORNER.jpg")
        print("  xxx_CWF_654-920.jpg")
        print("  xxx_D65_DESERT_SKY.jpg")
        print("（對色相正確檔名會用來訓練色名記憶）")
        return {"learned": 0, "retrained": False}

    new_rows: list[dict] = []
    source_paths: list[Path] = []
    for sample in collected:
        src = Path(sample["path"])
        source_paths.append(src)
        stored_name = f"{sample['kind']}__{sample['suffix'].replace(' ', '_')}__{src.stem}{src.suffix}"
        dest = images_dir / stored_name
        if copy_images:
            if not dest.exists():
                shutil.copy2(src, dest)
            image_path = str(dest)
        else:
            image_path = str(src)

        new_rows.append(
            {
                "image_path": image_path,
                "kind": sample["kind"],
                "suffix": sample["suffix"],
                "source_folder": str(folder),
                "source_name": sample["filename"],
                "added_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    append_manifest(model_dir, new_rows)

    all_rows = load_manifest(model_dir)
    by_path: dict[str, dict] = {}
    for row in all_rows:
        by_path[row["image_path"]] = row
    unique_rows = [r for r in by_path.values() if Path(r["image_path"]).exists()]

    paths = [r["image_path"] for r in unique_rows]
    kind_labels = [r["kind"] for r in unique_rows]
    angle_rows = [r for r in unique_rows if r["kind"] == "angle" and r["suffix"] in ANGLE_LABELS]
    angle_paths = [r["image_path"] for r in angle_rows]
    angle_labels = [r["suffix"] for r in angle_rows]
    color_rows = [r for r in unique_rows if r["kind"] == "color"]

    kind_counts: dict[str, int] = {}
    for label in kind_labels:
        kind_counts[label] = kind_counts.get(label, 0) + 1
    angle_counts: dict[str, int] = {}
    for label in angle_labels:
        angle_counts[label] = angle_counts.get(label, 0) + 1
    color_name_counts: dict[str, int] = {}
    for row in color_rows:
        key = str(row.get("suffix") or "?")
        color_name_counts[key] = color_name_counts.get(key, 0) + 1

    print("=" * 50)
    print("模式:       學習模式")
    print(f"今次新增:   {len(new_rows)} 張")
    print(f"累計樣本:   {len(paths)} 張")
    print(f"種類分布:   {kind_counts}")
    print(f"角度分布:   {angle_counts}")
    print(f"對色分布:   {color_name_counts}")
    print("=" * 50)

    result: dict = {
        "learned": len(new_rows),
        "total_samples": len(paths),
        "kind_counts": kind_counts,
        "angle_counts": angle_counts,
        "color_name_counts": color_name_counts,
        "retrained_kind": False,
        "retrained_angle": False,
        "retrained_color_names": False,
    }

    if len(set(kind_labels)) >= 2 and len(paths) >= 4:
        kind_path = default_simple_model_path(model_dir)
        kind_metrics = train_simple_kind_model(paths, kind_labels, kind_path)
        result["retrained_kind"] = True
        result["kind_metrics"] = kind_metrics
        result["kind_model"] = str(kind_path)
        print("角度/對色 模型訓練完成：")
        print(json.dumps(kind_metrics, indent=2, ensure_ascii=False))
    else:
        print("提示: 需要同時有角度相同對色相樣本，先可以訓練種類模型。")

    if len(set(angle_labels)) >= 2 and len(angle_paths) >= 4:
        angle_path = default_angle_model_path(model_dir)
        angle_metrics = train_simple_angle_model(angle_paths, angle_labels, angle_path)
        result["retrained_angle"] = True
        result["angle_metrics"] = angle_metrics
        result["angle_model"] = str(angle_path)
        print("角度細分 (AS/FRONT/SIDE/CORNER) 訓練完成：")
        print(json.dumps(angle_metrics, indent=2, ensure_ascii=False))
    else:
        print("提示: 角度細分需要至少兩種（AS/FRONT/SIDE/CORNER）先可以訓練。")

    if color_rows:
        print(f"對色相名記憶：用 {len(color_rows)} 張正確色名樣本重建…")
        memory = rebuild_color_memory(model_dir, color_rows, run_ocr=True, build_embeddings=True)
        result["retrained_color_names"] = True
        result["color_memory_entries"] = len(memory)
        result["color_memory_codes"] = len(memory.by_code)
        print(
            f"對色相名記憶完成：{len(memory)} 張樣本，"
            f"{len(memory.by_code)} 個色號對照"
        )
    else:
        print("提示: 未有對色相樣本，跳過色名記憶（可放 xxx_D65_DESERT_SKY.jpg 等）。")

    # Samples are already copied into learn_bank; clear the user-facing learn folder.
    cleanup = cleanup_learn_folder(folder, source_paths)
    result["cleaned_learn_folder"] = cleanup
    print(f"已清空學習資料夾：刪除 {cleanup['deleted']} 個檔案")
    if cleanup["failed"]:
        print(f"警告: 有 {cleanup['failed']} 個檔案刪除失敗")

    return result
