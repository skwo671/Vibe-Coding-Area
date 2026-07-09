@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "dist\PVH-Rename-Portable\rename_here.bat" (
    call "dist\PVH-Rename-Portable\rename_here.bat"
    exit /b
)

if exist ".venv\Scripts\python.exe" (
    set PYTHONPATH=%~dp0
    .venv\Scripts\python.exe scripts\rename_folder.py --apply --no-report --confidence 0.0
) else (
    set PYTHONPATH=%~dp0
    python scripts\rename_folder.py --apply --no-report --confidence 0.0
)

pause
