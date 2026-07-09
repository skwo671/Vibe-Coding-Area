@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   PVH 圖片改名工具 - Windows 打包
echo ========================================
echo.

where py >nul 2>&1
if %errorlevel%==0 (
    set PY=py -3.10
) else (
    set PY=python
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] 建立虛擬環境...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo 失敗：請先安裝 Python 3.10+  https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

echo [2/4] 安裝依賴（CPU 版 PyTorch，約需數分鐘）...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
pip install pyinstaller

if not exist "models\suffix_classifier\hierarchical_classifier.joblib" (
    echo.
    echo 警告：找不到訓練模型，請先執行：
    echo   python scripts\train_model.py
    echo.
    pause
)

echo [3/4] 下載 CLIP 模型（首次約 1GB，之後會快取）...
python -c "from transformers import CLIPModel, CLIPProcessor; CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32'); CLIPModel.from_pretrained('openai/clip-vit-base-patch32'); print('CLIP OK')"

echo [4/4] 打包成 .exe ...
python scripts\build_portable.py --bundle-clip

echo.
echo ========================================
echo   完成！
echo   輸出資料夾: dist\PVH-Rename-Portable
echo   壓縮檔:     dist\PVH-Rename-Portable.zip
echo ========================================
echo.
echo 使用方法：
echo   1. 將 dist\PVH-Rename-Portable 整個資料夾複製到圖片目錄
echo   2. 把圖片放入該資料夾
echo   3. 雙擊 rename_here.bat
echo.
echo 對色 OCR 需安裝 Tesseract：
echo   https://github.com/UB-Mannheim/tesseract/wiki
echo.
pause
