@echo off
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
echo 已準備完成。
echo 請確認 AI設定.txt 內容為：
echo   enabled=1
echo   base_url=http://127.0.0.1:11434/v1
echo   model=llava
echo   mode=always
echo.
echo 然後把 TDS + 圖片放入「待改名圖片」，執行「1_工作模式_自動改名.bat」
echo.
pause
