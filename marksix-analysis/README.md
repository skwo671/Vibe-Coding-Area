# 香港六合彩公開開獎紀錄分析（Python）

用公開歷史攪珠數據做**描述統計**：頻率、遺漏、奇偶／和值／區間分布，以及簡單隨機性檢驗。

> **呢個唔係預測工具。** 六合彩每期理論上獨立，冷熱號同遺漏值唔會提高下期中獎率。官方結果以[香港賽馬會](https://bet.hkjc.com/)為準。

## 數據來源

1. **預設**：[`icelam/mark-six-data-visualization`](https://github.com/icelam/mark-six-data-visualization) 嘅 `data/all.json`（社群鏡像，由 HKJC `getJSON.aspx` 定期抓取）
2. **可選**：本機若可連 HKJC，可加 `--prefer-hkjc` 試官方 JSON

## 安裝

```bash
cd marksix-analysis
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 使用

一次過下載 + 分析：

```bash
python run_all.py
```

或分步：

```bash
python fetch_data.py
python analyze.py
```

輸出會寫入 `data/` 同 `output/`：

| 檔案 | 內容 |
| --- | --- |
| `data/draws.csv` | 標準化開獎表 |
| `output/report.md` | 中文統計報告 |
| `output/frequency.csv` | 1–49 正碼／特別號碼頻率 |
| `output/gaps.csv` | 各號目前遺漏期數 |
| `output/*.png` | 頻率、遺漏、和值、奇偶圖 |

## 報告會計啲咩

- 正碼熱號／冷號（相對理論期望次數）
- 目前遺漏最長嘅號碼
- 奇數個數、六正碼和值、低／中／高區分布
- 歷史連號對（如 12–13）
- χ² 均勻性檢驗、和值高低 runs 檢驗（只係描述歷史，唔係選號）

預設只分析 **2002-07-04 起**（現行 49 選 6）。更早年代球數較少（45／47），若用全歷史會令 46–49 假性偏冷：

```bash
python analyze.py --since 2002-07-04   # 預設
python analyze.py --since ''           # 全歷史（僅供對照）
```

## 免責

本專案只供學習同統計練習。唔鼓勵以任何「必中算法」心態投注。
