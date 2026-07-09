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
        "pvh_filename.runtime",
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
    bat = portable / "rename_here.bat"
    bat.write_text(
        f"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
set HF_HOME=%~dp0models\\huggingface
set TRANSFORMERS_OFFLINE=1
set HF_HUB_OFFLINE=1
echo ========================================
echo   PVH 圖片檔名自動更正
echo ========================================
echo.
app\\{exe_name} "%~dp0" ^
  --model "%~dp0models\\suffix_classifier" ^
  --confidence 0.0 ^
  --apply ^
  --no-report ^
  --no-auto-train
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
  1. 將整個 PVH-Rename-Portable 資料夾複製到要改名的圖片目錄
  2. 把圖片（及 TDS 參考檔）放入此資料夾
  3. 雙擊 rename_here.bat

功能：
  - 直接改名（不輸出 rename_report.csv）
  - 角度相：CORNER / SIDE VIEW / FRONT&BACK / ACTUAL SIZE
  - 對色相：CWF_色號 或 D65_色號（需 OCR 讀到色卡色號）

注意：
  - {clip_note}
  - 對色 OCR 需安裝 Tesseract：
    https://github.com/UB-Mannheim/tesseract/wiki
  - 整個資料夾約 1.5-2 GB

手動執行：
  app\\{exe_name} "圖片資料夾" --model "models\\suffix_classifier" --apply --no-report
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
