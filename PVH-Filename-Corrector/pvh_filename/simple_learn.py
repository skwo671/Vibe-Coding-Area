from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from pvh_filename.simple_labels import iter_image_paths, parse_simple_label, split_prefix_and_label
from pvh_filename.simple_model import default_simple_model_path, train_simple_kind_model


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
    """Read user-corrected filenames as learning labels."""
    samples: list[dict] = []
    for path in iter_image_paths(folder):
        label = parse_simple_label(path.stem)
        if not label:
            continue
        _, parsed = split_prefix_and_label(path.stem)
        samples.append(
            {
                "path": str(path.resolve()),
                "kind": label.kind,
                "suffix": label.suffix,
                "filename": path.name,
            }
        )
    return samples


def learn_from_folder(folder: Path, model_dir: Path, *, copy_images: bool = True) -> dict:
    """
    Learning mode:
    1. Scan folder for correctly named images (_AS / _FRONT / _CWF_xxx).
    2. Add them into learn_bank.
    3. Retrain angle-vs-color AI model.
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
        print("  xxx_CWF_654-920.jpg")
        print("  xxx_CWF_19-1555.jpg")
        return {"learned": 0, "retrained": False}

    new_rows: list[dict] = []
    for sample in collected:
        src = Path(sample["path"])
        stored_name = f"{sample['kind']}__{src.stem}{src.suffix}"
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
    # Deduplicate by image_path keeping latest.
    by_path: dict[str, dict] = {}
    for row in all_rows:
        by_path[row["image_path"]] = row
    unique_rows = list(by_path.values())

    paths = [r["image_path"] for r in unique_rows if Path(r["image_path"]).exists()]
    labels = [r["kind"] for r in unique_rows if Path(r["image_path"]).exists()]

    print("=" * 50)
    print("模式:       學習模式")
    print(f"今次新增:   {len(new_rows)} 張")
    print(f"累計樣本:   {len(paths)} 張")
    kind_counts: dict[str, int] = {}
    for label in labels:
        kind_counts[label] = kind_counts.get(label, 0) + 1
    print(f"樣本分布:   {kind_counts}")
    print("=" * 50)

    if len(set(labels)) < 2:
        print("提示: 而家只有一種標籤。請同時提供角度相同對色相先可以訓練區分模型。")
        print("已保存學習樣本，等有兩類樣本後再跑學習模式。")
        return {
            "learned": len(new_rows),
            "total_samples": len(paths),
            "retrained": False,
            "reason": "need_both_kinds",
            "kind_counts": kind_counts,
        }

    model_path = default_simple_model_path(model_dir)
    metrics = train_simple_kind_model(paths, labels, model_path)
    print("訓練完成：")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return {
        "learned": len(new_rows),
        "total_samples": len(paths),
        "retrained": True,
        "metrics": metrics,
        "model": str(model_path),
    }
