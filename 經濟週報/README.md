# 經濟數據與AI板塊股票週報

本專案會每週自動彙整宏觀市場走勢、AI 相關股票新聞與情緒、技術面趨勢，輸出 Markdown 與 HTML 週報，並給出可參考之買進觀察清單。

## 功能
- 取得市場與產業走勢：`^NDX`（那斯達克100）、`SMH`（半導體ETF）、`XLK`（科技ETF）
- 聚合 AI 板塊新聞（RSS）：Google News、各公司關鍵字
- VADER 文字情緒分析，計算新聞正負向情緒
- 技術面趨勢指標（SMA/EMA、動能）
- 依據大環境趨勢與情緒，產生推薦標的（觀察/關注/可買）
- 週排程任務（APScheduler）

## 安裝

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用

- 立即產出一次報告（預設輸出到 `reports/`）：

```bash
python -m app.main run-once
```

- 以排程方式每週一 08:00 產出報告：

```bash
python -m app.main schedule
```

## 設定

調整 `app/config.py` 以修改追蹤的指數、ETF、AI 觀察名單與 RSS 來源、輸出路徑等。

可選：若要使用 FRED 等其它資料源，可在環境變數中配置 API KEY（目前程式會自動忽略未配置的來源）。

## 產出

- Markdown：`reports/YYYY-WW.md`
- HTML：`reports/YYYY-WW.html`

## 法律與風險聲明
本工具僅供教育與研究用途，不構成投資建議。投資有風險，入市需謹慎。



