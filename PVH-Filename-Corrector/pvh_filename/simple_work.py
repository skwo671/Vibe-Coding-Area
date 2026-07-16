from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import numpy as np

from pvh_filename.color_master import ColorMasterLookup, resolve_color_master
from pvh_filename.model import ClipEmbedder, HierarchicalClassifier, default_model_path
from pvh_filename.simple_ai_color import (
    AIColorConfig,
    AIPhotoResult,
    ai_status_message,
    classify_photo_with_ai,
    load_ai_config,
    read_color_card_with_ai,
    should_ask_ai,
    should_ask_ai_angle,
)
from pvh_filename.simple_angle_heuristics import looks_like_corner, looks_like_side_view
from pvh_filename.simple_as import has_two_similar_products
from pvh_filename.simple_color_memory import ColorNameMemory, default_color_memory_path
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
from pvh_filename.simple_ocr import ColorCardOCR, detect_color_card, tesseract_status_message


def _pick_color_name(
    color_code: str,
    raw_name: str,
    color_master: ColorMasterLookup | None,
    color_memory: ColorNameMemory | None = None,
) -> tuple[str, str]:
    """Return (display_name, source_tag). Prefer master, then learned memory."""
    if color_master and color_code:
        master_name = color_master.lookup_name(color_code) or ""
        if master_name:
            return master_name, "color_master"
    if color_memory and color_code:
        hit = color_memory.lookup_by_code(color_code)
        if hit and hit.name:
            return hit.name, "learned_code"
    if color_master and raw_name:
        fuzzy = color_master.fuzzy_lookup_name(raw_name) or ""
        if fuzzy:
            return fuzzy, "fuzzy_master"
    if color_memory and raw_name:
        # Exact / near match against learned names.
        needle = normalize_token(raw_name)
        for entry in color_memory.entries:
            learned = normalize_token(str(entry.get("name") or ""))
            if learned and learned == needle:
                return learned, "learned_name"
    if raw_name:
        return normalize_token(raw_name), "raw_name"
    return "", ""


def _resolve_color_identity(
    path: Path,
    color_ocr: ColorCardOCR | None,
    color_master: ColorMasterLookup | None,
    ai_cfg: AIColorConfig,
    *,
    color_memory: ColorNameMemory | None = None,
    embedding: np.ndarray | None = None,
) -> tuple[str, str, str, str, str]:
    """
    Build color suffix parts.

    Returns: color_code, light_source, suffix, source, reason
    """
    color_code = color_ocr.color_code if color_ocr else ""
    light = color_ocr.light_source if color_ocr else ""
    raw_name = color_ocr.color_name if color_ocr else ""
    name, name_src = _pick_color_name(color_code, raw_name, color_master, color_memory)
    used_ai = False
    ai_note = ""
    used_memory = name_src.startswith("learned")

    # Visual memory before AI when OCR is incomplete.
    if color_memory and embedding is not None and (not name or not color_code):
        hit = color_memory.lookup_by_embedding(embedding)
        if hit is not None:
            used_memory = True
            if hit.code and not color_code:
                color_code = hit.code
            if hit.name and not name:
                name = hit.name
                name_src = "learned_visual"
            if hit.light and not light:
                light = hit.light
            # If OCR missed everything but visual hit is strong, take full suffix.
            if not name and not color_code and hit.suffix:
                light = hit.light or "D65"
                if hit.name:
                    return (
                        hit.code,
                        light,
                        f"{light}_{hit.name}",
                        f"learned_visual/{light}",
                        "",
                    )
                if hit.code:
                    return (
                        hit.code,
                        light,
                        f"{light}_{hit.code}",
                        f"learned_visual/{light}",
                        "",
                    )

    ask = should_ask_ai(
        ai_cfg,
        has_ocr=color_ocr is not None,
        has_color_name=bool(name),
        has_color_code=bool(color_code),
    )

    if ask and ai_cfg.usable:
        master_names = color_master.unique_names() if color_master else []
        if color_memory:
            master_names = list(
                dict.fromkeys(
                    master_names
                    + [str(e.get("name")) for e in color_memory.entries if e.get("name")]
                )
            )
        hint = " ".join(x for x in (color_code, raw_name, name) if x)
        ai = read_color_card_with_ai(
            path,
            ai_cfg,
            hint_text=hint,
            master_names=master_names,
        )
        if ai is not None:
            ai_note = ai.note
            if ai.color_code or ai.color_name or ai.has_cwf_label:
                used_ai = True
                if ai.color_code:
                    color_code = ai.color_code
                if ai.color_name:
                    raw_name = ai.color_name
                if ai.has_cwf_label:
                    light = "CWF"
                elif not light:
                    light = ai.light_source
                name, name_src = _pick_color_name(
                    color_code, raw_name or name, color_master, color_memory
                )

    # After AI/OCR, fill name from learned code map if still missing.
    if color_memory and color_code and not name:
        hit = color_memory.lookup_by_code(color_code)
        if hit and hit.name:
            name = hit.name
            name_src = "learned_code"
            used_memory = True
            if hit.light and not light:
                light = hit.light

    if not color_code and not name:
        return "", "", "", "ai_failed" if used_ai else "no_color", ai_note or "讀唔到色號/色名"

    if not light:
        light = "D65"

    if name:
        suffix = f"{light}_{name}"
        bits = ["ocr"]
        if used_ai:
            bits.append("ai")
        if used_memory or name_src.startswith("learned"):
            bits.append(name_src if name_src.startswith("learned") else "learned")
        else:
            bits.append(name_src or "name")
        source = "+".join(dict.fromkeys(bits)) + f"/{light}"
    else:
        suffix = f"{light}_{color_code}"
        bits = ["ocr"]
        if used_ai:
            bits.append("ai")
        bits.append("color_code")
        source = "+".join(bits) + f"/{light}"
    return color_code, light, suffix, source, ""


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


def _apply_ai_photo_result(
    ai: AIPhotoResult,
    color_master: ColorMasterLookup | None,
    color_memory: ColorNameMemory | None = None,
) -> tuple[str, str, str, str, str, str]:
    """
    Convert AI photo result into rename fields.

    Returns: final_kind, color_code, light_source, suffix, source, reason
    """
    if ai.usable_color:
        light = "CWF" if ai.has_cwf_label else (ai.light_source or "D65")
        name, name_src = _pick_color_name(
            ai.color_code, ai.color_name, color_master, color_memory
        )
        if name:
            return (
                "color",
                ai.color_code,
                light,
                f"{light}_{name}",
                f"ai+{name_src or 'name'}/{light}",
                "",
            )
        if ai.color_code:
            return (
                "color",
                ai.color_code,
                light,
                f"{light}_{ai.color_code}",
                f"ai+color_code/{light}",
                "",
            )
        return "color", "", light, "", "ai_color_incomplete", ai.note or "AI 判斷為對色相但缺色號/色名"

    if ai.usable_angle:
        return "angle", "", "", ai.angle, f"ai_angle/{ai.angle}", ""

    return "", "", "", "", "ai_unusable", ai.note or "AI 未能分類"


def _resolve_angle_suffix(
    path: Path,
    embedding: np.ndarray | None,
    angle_clf: SimpleKindClassifier | None,
    legacy: HierarchicalClassifier | None,
    ai_cfg: AIColorConfig | None = None,
    color_master: ColorMasterLookup | None = None,
    color_memory: ColorNameMemory | None = None,
) -> tuple[str, str]:
    """Pick AS / FRONT / SIDE / CORNER for an angle shot."""
    if has_two_similar_products(path):
        local_suffix, local_source = "AS", "duplicate_pattern"
    elif angle_clf is not None and embedding is not None:
        labels, confs = angle_clf.predict_kind(embedding.reshape(1, -1))
        label = normalize_token(labels[0])
        if label in ANGLE_LABELS and confs[0] >= 0.35:
            local_suffix, local_source = label, "angle_model"
        else:
            local_suffix, local_source = "", ""
    else:
        local_suffix, local_source = "", ""

    if not local_suffix and legacy is not None and embedding is not None:
        suffixes, kinds, confs = legacy.predict(embedding.reshape(1, -1))
        if kinds and kinds[0] == "angle":
            mapped = _map_legacy_angle(suffixes[0])
            if mapped in ANGLE_LABELS:
                local_suffix, local_source = mapped, "legacy_angle_model"

    if not local_suffix:
        if looks_like_side_view(path):
            local_suffix, local_source = "SIDE", "heuristic_side"
        elif looks_like_corner(path):
            local_suffix, local_source = "CORNER", "heuristic_corner"
        else:
            local_suffix, local_source = "FRONT", "single_product"

    if ai_cfg and should_ask_ai_angle(ai_cfg, local_suffix=local_suffix, local_source=local_source):
        master_names = color_master.unique_names() if color_master else []
        if color_memory:
            master_names = list(
                dict.fromkeys(
                    master_names
                    + [str(e.get("name")) for e in color_memory.entries if e.get("name")]
                )
            )
        ai = classify_photo_with_ai(
            path,
            ai_cfg,
            master_names=master_names,
            hint_text=f"local_guess={local_suffix}/{local_source}",
        )
        if ai is not None:
            if ai.usable_angle:
                return ai.angle, f"ai_angle/{ai.angle}"
            if ai.usable_color:
                # Rare: local thought angle, AI says color — leave angle fallback but mark.
                kind, code, light, suffix, source, _reason = _apply_ai_photo_result(
                    ai, color_master, color_memory
                )
                if suffix and kind == "color":
                    return suffix, source

    return local_suffix, local_source


def predict_work_folder(
    folder: Path,
    model_dir: Path,
    *,
    apply: bool = True,
    write_report: bool = True,
    ai_config: AIColorConfig | None = None,
) -> dict:
    folder = folder.resolve()
    images = iter_image_paths(folder)
    prefix = find_tds_prefix(folder) or folder.name
    color_master = resolve_color_master(folder)
    ai_cfg = ai_config if ai_config is not None else load_ai_config(folder)
    color_memory = ColorNameMemory.load(default_color_memory_path(model_dir))

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

    need_embeddings = bool(
        images and (kind_clf or angle_clf or legacy or (color_memory and color_memory.embeddings is not None))
    )
    if need_embeddings:
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
        color_ocr = detect_color_card(path)
        color_code = color_ocr.color_code if color_ocr else ""
        suffix = ""
        source = "model"
        reason = ""
        final_kind = kind
        light_source = color_ocr.light_source if color_ocr else ""
        embedding = emb_map.get(str(path))

        # mode=always: let AI look at every photo first (color + angle).
        if ai_cfg.usable and ai_cfg.mode == "always":
            master_names = color_master.unique_names() if color_master else []
            if color_memory:
                master_names = list(
                    dict.fromkeys(
                        master_names
                        + [str(e.get("name")) for e in color_memory.entries if e.get("name")]
                    )
                )
            hint = " ".join(
                x
                for x in (
                    f"model_kind={kind}",
                    f"ocr_code={color_code}" if color_code else "",
                    f"ocr_name={color_ocr.color_name}" if color_ocr and color_ocr.color_name else "",
                )
                if x
            )
            ai = classify_photo_with_ai(path, ai_cfg, master_names=master_names, hint_text=hint)
            if ai is not None:
                (
                    ai_kind,
                    ai_code,
                    ai_light,
                    ai_suffix,
                    ai_source,
                    ai_reason,
                ) = _apply_ai_photo_result(ai, color_master, color_memory)
                if ai_suffix:
                    final_kind = ai_kind or final_kind
                    color_code = ai_code or color_code
                    light_source = ai_light or light_source
                    suffix = ai_suffix
                    source = ai_source
                    reason = ""
                elif ai_kind == "color":
                    final_kind = "color"
                    reason = ai_reason

        # Color / angle fallback. In always mode we already asked AI once above —
        # keep local OCR + models here to avoid a second paid API call.
        local_ai = (
            AIColorConfig(enabled=False, mode="off", source=ai_cfg.source)
            if (ai_cfg.usable and ai_cfg.mode == "always")
            else ai_cfg
        )

        if not suffix:
            try_color = color_ocr is not None or kind == "color" or final_kind == "color"
            if try_color:
                (
                    color_code,
                    light_source,
                    color_suffix,
                    color_source,
                    color_reason,
                ) = _resolve_color_identity(
                    path,
                    color_ocr,
                    color_master,
                    local_ai,
                    color_memory=color_memory,
                    embedding=embedding,
                )
                if color_suffix:
                    final_kind = "color"
                    suffix = color_suffix
                    source = color_source
                    reason = ""
                elif kind == "color" or color_ocr is not None or final_kind == "color":
                    final_kind = "color"
                    source = "model_color_no_ocr" if color_ocr is None else color_source
                    reason = color_reason or "模型判斷為對色相，但讀唔到色號/色名"

        if not suffix and final_kind != "color":
            final_kind = "angle"
            suffix, source = _resolve_angle_suffix(
                path,
                embedding,
                angle_clf,
                legacy,
                ai_cfg=local_ai,
                color_master=color_master,
                color_memory=color_memory,
            )
            # If angle AI redirected to a color suffix, mark as color.
            if suffix.startswith(("CWF_", "D65_", "UV_")):
                final_kind = "color"

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
                "light_source": light_source,
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
            "light_source",
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
        "ai_color": ai_status_message(ai_cfg),
        "ai_mode": ai_cfg.mode if ai_cfg.usable else "off",
        "model": str(kind_path) if kind_path.exists() else None,
        "angle_model": str(angle_path) if angle_path.exists() else None,
        "color_memory": (
            f"{len(color_memory)} samples / {len(color_memory.by_code)} codes"
            if color_memory
            else None
        ),
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
    print(summary["ai_color"])
    if color_memory:
        print(
            f"色名記憶:   {len(color_memory)} 張 / {len(color_memory.by_code)} 個色號"
        )
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
