#!/usr/bin/env python3
"""Portable entry point: rename images in a folder using the trained PVH model."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pvh_filename.auto_train import record_run_and_maybe_train
from pvh_filename.ocr import tesseract_status_message
from pvh_filename.predict import rename_folder
from pvh_filename.runtime import (
    default_model_dir,
    default_target_folder,
    is_frozen,
    portable_root,
)


def configure_offline_models() -> None:
    if not is_frozen():
        return
    hf_home = portable_root() / "models" / "huggingface"
    if hf_home.exists():
        os.environ["HF_HOME"] = str(hf_home)
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"

DEFAULT_TRAINING_DATA = Path(__file__).resolve().parents[1] / "data/PVH EU"


def pause_if_windows() -> None:
    if is_frozen() and sys.platform == "win32":
        input("\n按 Enter 關閉...")


def main() -> int:
    configure_offline_models()
    parser = argparse.ArgumentParser(
        description="PVH 圖片檔名自動更正 — 將此工具放在目標資料夾內執行，或指定資料夾路徑。"
    )
    parser.add_argument(
        "folder",
        nargs="?",
        type=Path,
        default=None,
        help="要處理的資料夾（預設：工具所在目錄）",
    )
    parser.add_argument("--model", type=Path, default=default_model_dir())
    parser.add_argument("--confidence", type=float, default=0.55, help="自動改名最低信心（0-1）")
    parser.add_argument("--apply", action="store_true", help="直接改名（預設只出報告）")
    parser.add_argument("--report", type=Path, default=None, help="報告 CSV 路徑")
    parser.add_argument("--no-report", action="store_true", help="唔輸出 rename_report.csv")
    parser.add_argument("--auto-train-every", type=int, default=5, help="每運行 N 次自動更新模型")
    parser.add_argument("--training-data", type=Path, default=DEFAULT_TRAINING_DATA)
    parser.add_argument("--no-auto-train", action="store_true", help="今次唔計入/觸發自動訓練")
    parser.add_argument(
        "--color-master",
        type=Path,
        default=None,
        help="Archroma 色號對照表 xlsx（預設自動搜尋資料夾內或 reference/）",
    )
    args = parser.parse_args()

    folder = args.folder or default_target_folder()
    if not folder.is_dir():
        print(f"找不到資料夾: {folder}")
        pause_if_windows()
        return 1

    model_file = args.model / "hierarchical_classifier.joblib"
    legacy = args.model / "suffix_classifier.joblib"
    if not model_file.exists() and not legacy.exists():
        print(f"找不到模型，請先訓練:\n  python scripts/train_model.py")
        print(f"預期位置: {model_file}")
        pause_if_windows()
        return 1

    print(f"處理資料夾: {folder}")
    print(f"使用模型:   {args.model}")
    if args.color_master:
        print(f"色號對照表: {args.color_master}")
    print(f"模式:       {'直接改名' if args.apply else '只出報告（加 --apply 才改名）'}")
    if args.no_report:
        print("報告:       不輸出 CSV")
    else:
        print("報告:       待改名圖片/rename_report.csv")
    print(tesseract_status_message())
    print()

    summary = rename_folder(
        folder,
        args.model,
        apply=args.apply,
        confidence=args.confidence,
        report_path=args.report,
        write_report=not args.no_report,
        color_master_path=args.color_master,
    )

    if not args.no_auto_train:
        state = record_run_and_maybe_train(
            model_dir=args.model,
            training_data=args.training_data,
            every=args.auto_train_every,
            enabled=True,
        )
        summary["runs_until_auto_train"] = max(
            args.auto_train_every - int(state.get("runs_since_train", 0)), 0
        )
        summary["auto_train_triggered"] = state.get("auto_train_triggered", False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print()
    if not args.apply and summary["auto_rename"]:
        print("提示: 請先檢查 rename_report.csv，確認無誤後加 --apply 再執行。")

    pause_if_windows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
