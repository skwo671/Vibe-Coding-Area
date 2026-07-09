#!/bin/bash
cd "$(dirname "$0")"
PROJECT="/Users/bigbrownbear/Desktop/Vibe-Coding-Area/PVH-Filename-Corrector"
export PYTHONPATH="$PROJECT"
clear
echo "========================================"
echo "  PVH 圖片檔名自動更正 - 示範"
echo "========================================"
echo ""
echo "處理資料夾: 待改名圖片"
echo "（首次執行需載入 AI 模型，約 1-3 分鐘）"
echo ""
"$PROJECT/.venv/bin/python" "$PROJECT/scripts/rename_folder.py" "/Users/bigbrownbear/Desktop/Vibe-Coding-Area/PVH-Filename-Corrector/demo-run/待改名圖片" \
  --model "$PROJECT/models/suffix_classifier" \
  --training-data "$PROJECT/data/PVH EU" \
  --confidence 0.0 \
  --apply \
  --no-report
echo ""
echo "完成！"
echo "- 對照表:   亂碼對照表.txt"
echo ""
read -p "按 Enter 關閉..."
