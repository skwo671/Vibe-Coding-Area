#!/usr/bin/env python3
"""Build a portable Windows .exe package with PyInstaller."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "PVH-Rename-Portable"
APP_NAME = "PVH-Rename"
CLIP_REPO = "models--openai--clip-vit-base-patch32"


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing pyinstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def huggingface_hub_dir() -> Path:
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface"))
    return hf_home / "hub"


def bundle_clip_cache(portable: Path) -> bool:
    clip_src = huggingface_hub_dir() / CLIP_REPO
    if not clip_src.exists():
        print(f"CLIP cache not found: {clip_src}")
        print("Run build_windows.bat or download CLIP before building.")
        return False

    dst = portable / "models" / "huggingface" / "hub" / CLIP_REPO
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(clip_src, dst)
    print(f"Bundled CLIP cache -> {dst}")
    return True


def build_executable() -> Path:
    ensure_pyinstaller()
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name",
        APP_NAME,
        "--paths",
        str(ROOT),
        "--collect-all",
        "transformers",
        "--collect-all",
        "torch",
        "--collect-all",
        "sklearn",
        "--hidden-import",
        "pvh_filename",
        "--hidden-import",
        "pvh_filename.predict",
        "--hidden-import",
        "pvh_filename.model",
        "--hidden-import",
        "pvh_filename.ocr",
        "--hidden-import",
        "pvh_filename.auto_train",
        "--hidden-import",
        "pvh_filename.filenames",
        "--hidden-import",
        "pvh_filename.dataset",
        "--hidden-import",
        "pvh_filename.actual_size",
        "--hidden-import",
        "openpyxl",
        "--hidden-import",
        "cv2",
        "--hidden-import",
        "pytesseract",
        "--hidden-import",
        "PIL",
        str(ROOT / "scripts" / "rename_folder.py"),
    ]
    subprocess.check_call(cmd, cwd=ROOT)
    return ROOT / "dist" / APP_NAME


def write_launchers(portable: Path, exe_name: str) -> None:
    work_dir = portable / "待改名圖片"
    work_dir.mkdir(exist_ok=True)
    (work_dir / "請將 TDS 參考檔同未改名圖片放喺呢度.txt").write_text(
        """請將以下檔案放入此資料夾：
  - 已改好名嘅 TDS 參考檔（檔名包含 _TDS，例如 xxx_TDS.pdf）
  - 所有未改名的圖片
  - （可選）Archroma 色號對照表 xlsx

放好後，返回上一層雙擊 rename_here.bat 即可自動改名。
對色圖片會 OCR 讀色號，再查表改成色名（例如 CWF_FAIRWAY GREEN）。
""",
        encoding="utf-8",
    )

    bat = portable / "rename_here.bat"
    bat.write_text(
        f"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
set HF_HOME=%~dp0models\\huggingface
set TRANSFORMERS_OFFLINE=1
set HF_HUB_OFFLINE=1

set "TARGET=%~dp0"
if exist "%~dp0待改名圖片\\" set "TARGET=%~dp0待改名圖片"

echo ========================================
echo   PVH 圖片檔名自動更正
echo ========================================
echo.
echo 處理資料夾: %TARGET%
echo.
app\\{exe_name} "%TARGET%" ^
  --model "%~dp0models\\suffix_classifier" ^
  --color-master "%~dp0reference\\Archroma_Color_Standard_Master_List_Shane.xlsx" ^
  --confidence 0.0 ^
  --apply ^
  --no-auto-train
echo.
echo 如有圖片未改名，請睇「待改名圖片\\rename_report.csv」
echo.
pause
""",
        encoding="utf-8",
    )


def write_readme(portable: Path, exe_name: str, has_clip: bool) -> None:
    clip_note = (
        "已內建 CLIP 模型，可離線使用。"
        if has_clip
        else "首次執行需聯網下載 CLIP 模型（約 1GB）。"
    )
    readme = portable / "使用說明.txt"
    readme.write_text(
        f"""PVH 圖片檔名自動更正工具（Windows）
================================

使用方法：
  1. 打開「待改名圖片」資料夾
  2. 放入 TDS 參考檔（檔名含 _TDS）同所有未改名圖片
  3. 雙擊 rename_here.bat

程式會自動：
  - 從 TDS 檔讀取正確產品前綴
  - 辨識每張圖係角度相定對色相
  - 直接改名（已正確嘅圖片會跳過）

功能：
  - 角度相：CORNER / SIDE VIEW / FRONT&BACK / AS（Actual Size，兩個相同圖案）
  - 對色相：OCR 讀色號 → 查 Archroma 色號表 → 改成 CWF_色名 / D65_色名

注意：
  - {clip_note}
  - 對色 OCR 需安裝 Tesseract：
    https://github.com/UB-Mannheim/tesseract/wiki
  - TDS 同圖片必須放喺同一個資料夾

手動執行：
  app\\{exe_name} "待改名圖片" --model "models\\suffix_classifier" --apply --no-report
""",
        encoding="utf-8",
    )


def make_zip(portable: Path) -> Path:
    zip_base = portable.parent / portable.name
    if Path(f"{zip_base}.zip").exists():
        Path(f"{zip_base}.zip").unlink()
    archive = shutil.make_archive(str(zip_base), "zip", portable.parent, portable.name)
    return Path(archive)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PVH portable Windows package")
    parser.add_argument(
        "--bundle-clip",
        action="store_true",
        help="Bundle HuggingFace CLIP cache for offline use",
    )
    parser.add_argument(
        "--no-bundle-clip",
        action="store_true",
        help="Skip bundling CLIP (smaller package, needs internet on first run)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bundle_clip = args.bundle_clip or not args.no_bundle_clip

    if platform.system() != "Windows":
        print("=" * 50)
        print("你而家用緊 Mac/Linux，無法直接產生 Windows .exe。")
        print()
        print("請用以下任一方法取得 Windows .exe：")
        print("  1. 將專案複製去 Windows，雙擊 build_windows.bat")
        print("  2. GitHub Actions：推送後到 Actions 頁下載 artifact")
        print("=" * 50)
        if platform.system() == "Darwin":
            sys.exit(1)

    model_src = ROOT / "models" / "suffix_classifier" / "hierarchical_classifier.joblib"
    if not model_src.exists():
        print(f"ERROR: Missing model: {model_src}")
        print("Run: python scripts/train_model.py")
        sys.exit(1)

    built_dir = build_executable()
    exe_name = "PVH-Rename.exe"

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    shutil.copytree(built_dir, DIST / "app")

    model_dir = ROOT / "models" / "suffix_classifier"
    shutil.copytree(model_dir, DIST / "models" / "suffix_classifier")

    color_master = ROOT / "reference" / "Archroma_Color_Standard_Master_List_Shane.xlsx"
    if color_master.exists():
        shutil.copytree(ROOT / "reference", DIST / "reference")

    has_clip = False
    if bundle_clip:
        has_clip = bundle_clip_cache(DIST)

    write_launchers(DIST, exe_name)
    write_readme(DIST, exe_name, has_clip)

    zip_path = make_zip(DIST)
    print(f"\nPortable package: {DIST}")
    print(f"Zip archive:      {zip_path}")


if __name__ == "__main__":
    main()
