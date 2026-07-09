#!/usr/bin/env python3
"""Create a local demo folder with scrambled image names and a one-click runner."""

from __future__ import annotations

import random
import shutil
import string
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SOURCE_FOLDER = PROJECT / "data/PVH EU/009268_THOMG-010013-25_RWB_75MMX40MM_1ST"
DEMO_ROOT = PROJECT / "demo-run"
IMAGE_DIR = DEMO_ROOT / "待改名圖片"
PREFIX = "009268_THOMG-010013-25_RWB_75MMX40MM_1ST"


def random_name(ext: str, used: set[str]) -> str:
    while True:
        body = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        name = f"{body}{ext}"
        if name not in used:
            used.add(name)
            return name


def main() -> None:
    if not SOURCE_FOLDER.is_dir():
        raise SystemExit(f"Source folder not found: {SOURCE_FOLDER}")

    if DEMO_ROOT.exists():
        shutil.rmtree(DEMO_ROOT)
    IMAGE_DIR.mkdir(parents=True)

    images = sorted(
        p
        for p in SOURCE_FOLDER.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if not images:
        raise SystemExit("No images found in source folder.")

    used: set[str] = set()
    mapping_lines = ["# 示範用：原本檔名 -> 亂碼檔名", ""]

    for src in images:
        gibberish = random_name(src.suffix, used)
        shutil.copy2(src, IMAGE_DIR / gibberish)
        mapping_lines.append(f"{gibberish}\t<- was\t{src.name}")

    tds_anchor = IMAGE_DIR / f"{PREFIX}_TDS.txt"
    tds_anchor.write_text(
        "TDS reference anchor for demo.\n"
        "This file provides the correct product prefix for renaming.\n",
        encoding="utf-8",
    )

    run_command = DEMO_ROOT / "按此執行改名.command"
    run_command.write_text(
        f"""#!/bin/bash
cd "$(dirname "$0")"
PROJECT="{PROJECT}"
export PYTHONPATH="$PROJECT"
clear
echo "========================================"
echo "  PVH 圖片檔名自動更正 - 示範"
echo "========================================"
echo ""
echo "處理資料夾: {IMAGE_DIR.name}"
echo "（首次執行需載入 AI 模型，約 1-3 分鐘）"
echo ""
"$PROJECT/.venv/bin/python" "$PROJECT/scripts/rename_folder.py" "{IMAGE_DIR}" \\
  --model "$PROJECT/models/suffix_classifier" \\
  --training-data "$PROJECT/data/PVH EU" \\
  --confidence 0.0 \\
  --apply \\
  --no-report
echo ""
echo "完成！"
echo "- 對照表:   亂碼對照表.txt"
echo ""
read -p "按 Enter 關閉..."
""",
        encoding="utf-8",
    )
    run_command.chmod(0o755)

    readme = DEMO_ROOT / "使用說明.txt"
    readme.write_text(
        """PVH 圖片檔名更正 - 本地示範
========================

這個資料夾係俾你試用嘅示範環境。

內容：
  待改名圖片/     <- 9 張圖片（檔名已改成亂碼）+ 1 個 TDS 前綴參考檔
  亂碼對照表.txt  <- 亂碼同原本正確檔名嘅對照
  按此執行改名.command <- 雙擊執行（Mac）

使用方法：
  1. 雙擊「按此執行改名.command」
  2. 如 Mac 提示無法開啟：右鍵 -> 打開 -> 打開
  3. 等程式跑完（首次約 1-3 分鐘）
  4. 檢查「待改名圖片」入面嘅檔名是否已改返

備註：
  - Demo 係直接改名，不輸出 rename_report.csv
  - 每運行 5 次會自動重新訓練模型一次

來源產品：
  009268_THOMG-010013-25_RWB_75MMX40MM_1ST
""",
        encoding="utf-8",
    )

    mapping_file = DEMO_ROOT / "亂碼對照表.txt"
    mapping_file.write_text("\n".join(mapping_lines) + "\n", encoding="utf-8")

    print(f"Demo ready: {DEMO_ROOT}")
    print(f"Images: {len(images)} scrambled")
    print(f"Double-click: {run_command.name}")


if __name__ == "__main__":
    main()
