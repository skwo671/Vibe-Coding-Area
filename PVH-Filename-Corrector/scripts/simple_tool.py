#!/usr/bin/env python3
"""Simple PVH rename tool: work mode + learn mode."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pvh_filename.runtime import default_model_dir, default_target_folder, is_frozen, portable_root
from pvh_filename.simple_learn import learn_from_folder
from pvh_filename.simple_work import predict_work_folder


def configure_offline_models() -> None:
    if not is_frozen():
        return
    hf_home = portable_root() / "models" / "huggingface"
    if hf_home.exists():
        os.environ["HF_HOME"] = str(hf_home)
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"


def pause_if_windows() -> None:
    if is_frozen() and sys.platform == "win32":
        input("\n按 Enter 關閉...")


def resolve_target(folder: Path | None) -> Path:
    if folder is not None:
        return folder
    cwd = Path.cwd()
    candidate = cwd / "待改名圖片"
    if candidate.is_dir():
        return candidate
    if is_frozen():
        root = portable_root()
        packaged = root / "待改名圖片"
        if packaged.is_dir():
            return packaged
        return cwd
    return default_target_folder()


def main() -> int:
    configure_offline_models()
    parser = argparse.ArgumentParser(description="PVH 簡化改名工具：工作模式 / 學習模式")
    parser.add_argument("mode", choices=["work", "learn"], help="work=自動改名, learn=從正確檔名學習")
    parser.add_argument("folder", nargs="?", type=Path, default=None)
    parser.add_argument("--model", type=Path, default=default_model_dir())
    parser.add_argument("--dry-run", action="store_true", help="工作模式只報告唔改名")
    args = parser.parse_args()

    folder = resolve_target(args.folder)
    if not folder.is_dir():
        print(f"找不到資料夾: {folder}")
        pause_if_windows()
        return 1

    print(f"模式: {args.mode}")
    print(f"資料夾: {folder}")
    print(f"模型目錄: {args.model}")
    print()

    if args.mode == "work":
        summary = predict_work_folder(
            folder,
            args.model,
            apply=not args.dry_run,
            write_report=True,
        )
    else:
        summary = learn_from_folder(folder, args.model)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    pause_if_windows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
