@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONPATH=%~dp0
set "TARGET=%~dp0學習樣本"
if not exist "%TARGET%" mkdir "%TARGET%"
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe scripts\simple_tool.py learn "%TARGET%" --model models\suffix_classifier
) else (
  python scripts\simple_tool.py learn "%TARGET%" --model models\suffix_classifier
)
pause
