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
        return False
    dst = portable / "models" / "huggingface" / "hub" / CLIP_REPO
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(clip_src, dst)
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
        "pvh_filename.simple_work",
        "--hidden-import",
        "pvh_filename.simple_learn",
        "--hidden-import",
        "pvh_filename.simple_model",
        "--hidden-import",
        "pvh_filename.simple_labels",
        "--hidden-import",
        "pvh_filename.simple_ocr",
        "--hidden-import",
        "pvh_filename.simple_ai_color",
        "--hidden-import",
        "pvh_filename.simple_as",
        "--hidden-import",
        "pvh_filename.simple_angle_heuristics",
        "--hidden-import",
        "pvh_filename.model",
        "--hidden-import",
        "pvh_filename.color_master",
        "--hidden-import",
        "pvh_filename.runtime",
        "--hidden-import",
        "openpyxl",
        "--hidden-import",
        "cv2",
        "--hidden-import",
        "pytesseract",
        "--hidden-import",
        "PIL",
        str(ROOT / "scripts" / "simple_tool.py"),
    ]
    subprocess.check_call(cmd, cwd=ROOT)
    return ROOT / "dist" / APP_NAME


def write_launchers(portable: Path, exe_name: str) -> None:
    work_dir = portable / "待改名圖片"
    work_dir.mkdir(exist_ok=True)
    learn_dir = portable / "學習樣本"
    learn_dir.mkdir(exist_ok=True)

    (work_dir / "請將 TDS 同未改名圖片放喺呢度.txt").write_text(
        """工作模式資料夾：
  1. 放入 TDS 參考檔（檔名含 _TDS）
  2. 放入未改名圖片
  3. 返回上一層，雙擊「1_工作模式_自動改名.bat」
""",
        encoding="utf-8",
    )
    (learn_dir / "請將已改正確檔名嘅圖片放喺呢度.txt").write_text(
        """請將已改正確檔名嘅圖片放喺呢度，例如：
    產品前綴_AS.jpg
    產品前綴_FRONT.jpg
    產品前綴_SIDE.jpg
    產品前綴_CORNER.jpg
    產品前綴_CWF_654-920.jpg
  然後返回上一層，雙擊「2_學習模式_訓練模型.bat」
""",
        encoding="utf-8",
    )

    (portable / "1_工作模式_自動改名.bat").write_text(
        f"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
set HF_HOME=%~dp0models\\huggingface
set TRANSFORMERS_OFFLINE=1
set HF_HUB_OFFLINE=1
set "TARGET=%~dp0待改名圖片"
echo ========================================
echo   工作模式：自動改名
echo   （如用 AI：請先開 Ollama，見 0_準備Ollama_AI.bat）
echo ========================================
app\\{exe_name} work "%TARGET%" --model "%~dp0models\\suffix_classifier"
echo.
pause
""",
        encoding="utf-8",
    )

    (portable / "2_學習模式_訓練模型.bat").write_text(
        f"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
set HF_HOME=%~dp0models\\huggingface
set TRANSFORMERS_OFFLINE=1
set HF_HUB_OFFLINE=1
set "TARGET=%~dp0學習樣本"
echo ========================================
echo   學習模式：從正確檔名訓練
echo ========================================
app\\{exe_name} learn "%TARGET%" --model "%~dp0models\\suffix_classifier"
echo.
pause
""",
        encoding="utf-8",
    )

    (portable / "0_準備Ollama_AI.bat").write_text(
        """@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   準備本機 Ollama AI（睇圖改名）
echo ========================================
echo.
echo 1) 請先安裝 Ollama： https://ollama.com/
echo 2) 安裝後保持 Ollama 開住
echo 3) 本腳本會下載 vision 模型 llava
echo.

where ollama >nul 2>&1
if errorlevel 1 (
  echo [錯誤] 搵唔到 ollama 命令。
  echo 請先去 https://ollama.com/ 安裝，然後重新開 cmd 再跑此 bat。
  echo.
  pause
  exit /b 1
)

echo 檢查 Ollama 服務...
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
  echo [提示] Ollama 似乎未啟動，嘗試執行 ollama serve ...
  start "" ollama serve
  timeout /t 3 >nul
)

echo.
echo 下載／更新模型：llava
ollama pull llava
if errorlevel 1 (
  echo [錯誤] ollama pull llava 失敗
  pause
  exit /b 1
)

echo.
echo 已準備完成。請執行「1_工作模式_自動改名.bat」
echo.
pause
""",
        encoding="utf-8",
    )

    # Keep old name as alias to work mode.
    (portable / "rename_here.bat").write_text(
        '@echo off\r\ncall "%~dp01_工作模式_自動改名.bat"\r\n',
        encoding="utf-8",
    )


def write_readme(portable: Path, exe_name: str, has_clip: bool) -> None:
    clip_note = "已內建 CLIP 模型，可離線使用。" if has_clip else "首次執行需聯網下載 CLIP。"
    (portable / "使用說明.txt").write_text(
        f"""PVH 簡化改名工具（Windows）
========================

兩個模式：

1) 工作模式（自動改名）
   - 把 TDS + 未改名圖片放入「待改名圖片」
   - 雙擊 1_工作模式_自動改名.bat
   - 規則：
     * 對色相：有色號 + 有 CWF 標籤 → CWF；有色號但無 CWF → D65
     * 角度相 AS：兩個非常相近產品圖案
     * 角度相 FRONT：單一正面
     * 角度相 SIDE：側面
     * 角度相 CORNER：角落

2) 學習模式（不斷訓練）
   - 把你手動改正確嘅圖片放入「學習樣本」
     檔名例子：xxx_AS.jpg / xxx_FRONT.jpg / xxx_SIDE.jpg / xxx_CORNER.jpg / xxx_CWF_654-920.jpg
   - 雙擊 2_學習模式_訓練模型.bat
   - 程式會記住答案並重訓模型；完成後會刪除「學習樣本」內嘅圖片/檔案
     （說明用 .txt 會保留）

注意：
  - {clip_note}
  - 對色 OCR 需要 Tesseract：C:\\Program Files\\Tesseract-OCR
  - 色號表喺 reference\\ 資料夾
  - （可選）本機 Ollama AI 睇圖改名（免費、無地區限制）：
    安裝 https://ollama.com/ → 跑 0_準備Ollama_AI.bat → 保持 Ollama 開住
    AI設定.txt 預設 model=llava、mode=always（對色 + 角度）
    第一次下載模型需要網絡；之後可離線用


手動：
  app\\{exe_name} work "待改名圖片" --model models\\suffix_classifier
  app\\{exe_name} work "待改名圖片" --model models\\suffix_classifier --ai
  app\\{exe_name} learn "學習樣本" --model models\\suffix_classifier
""",
        encoding="utf-8",
    )


def make_zip(portable: Path) -> Path:
    zip_base = portable.parent / portable.name
    if Path(f"{zip_base}.zip").exists():
        Path(f"{zip_base}.zip").unlink()
    return Path(shutil.make_archive(str(zip_base), "zip", portable.parent, portable.name))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-clip", action="store_true")
    parser.add_argument("--no-bundle-clip", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bundle_clip = args.bundle_clip or not args.no_bundle_clip
    if platform.system() != "Windows":
        print("請喺 Windows 或用 GitHub Actions 打包 .exe")
        if platform.system() == "Darwin":
            sys.exit(1)

    model_src = ROOT / "models" / "suffix_classifier" / "hierarchical_classifier.joblib"
    if not model_src.exists():
        print(f"ERROR: Missing model: {model_src}")
        sys.exit(1)

    built_dir = build_executable()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    shutil.copytree(built_dir, DIST / "app")
    shutil.copytree(ROOT / "models" / "suffix_classifier", DIST / "models" / "suffix_classifier")
    color_master = ROOT / "reference" / "Archroma_Color_Standard_Master_List_Shane.xlsx"
    if color_master.exists():
        shutil.copytree(ROOT / "reference", DIST / "reference")
    has_clip = bundle_clip_cache(DIST) if bundle_clip else False
    write_launchers(DIST, "PVH-Rename.exe")
    write_readme(DIST, "PVH-Rename.exe", has_clip)
    example_ai = ROOT / "AI設定.example.txt"
    if example_ai.exists():
        shutil.copy2(example_ai, DIST / "AI設定.example.txt")
        # Ready-to-edit Gemini config (user fills api_key).
        shutil.copy2(example_ai, DIST / "AI設定.txt")
    zip_path = make_zip(DIST)
    print(f"Portable package: {DIST}")
    print(f"Zip archive:      {zip_path}")


if __name__ == "__main__":
    main()
