# Cursor Cloud Agent「潛力投資追蹤」摘要

- **Agent ID**：`bc-fece6ffe-c354-42b9-9c04-492873071f43`
- **Branch**：`cursor/market-scanner-1f43`｜**PR**：[#2](https://github.com/skwo671/Vibe-Coding-Area/pull/2)
- **時間**：約 **2026-07-04** 建立；artifact `workspace_files_20260708.tar.gz`（**2026-07-08**）；對話活躍至約 **2026-07-12**

## 用戶原始需求

1. 寫 Python 同時追蹤有潛力可買嘅**加密貨幣同美股**，條件：七日內 52 週新高；4 小時價在 MA10/20/50 上方；市值 >100M；並畫圖標示有利買入位。
2. 後續迭代：一周換手率 ≥5%（後放寬至 3%）；放寬 MA（只需 MA20+MA50）；日 K 平台分流（Crypto / 美股分表）；EMA/RSI/布林/OBV 圖同告警；圖表買入區、logo、檔名；報告電郵至 `skwo671@gmail.com`；Cloud Environment / `.env` 設定說明。

## Agent 產出

- **掃描器**：`Trading Bot/app/market_scanner.py`（Yahoo、4h）→ 後期主推 `app/platform_scanner.py`（Crypto：**CoinGecko**；美股：**Finnhub**/Yahoo；日 K）。
- **輸出**：`Cursor output/` 下 CSV、圖表、`report/market_scanner_report.html` + `.zip`。
- **後期報告候選（引述）**：美股 **Visa (V)、Palo Alto Networks (PANW)、CrowdStrike (CRWD)、GE Vernova (GEV)**；加密圖表／技術分析提及 **LAB、BUILDon、THORChain、Arbitrum (ARB)**。
- **電郵**：報告已生成，但環境**未設 SMTP**，未能寄出。

## 策略重點（技術篩選，非投資建議）

- 核心：52 週新高（7 日內）+ 趨勢 MA + 市值 + 一周換手率。
- 買入區：早期 MA10–MA20；後期改 **MA20–MA50 回踩**，止蝕參考 MA50 下方約 2%。
- Crypto 告警：EMA20/50 交叉、布林 Squeeze、RSI 超買／超賣。

## 持股／「投資總經理」

- Transcript **無**「投資總經理」、持股或投資組合紀錄；結果屬 **watchlist／技術篩選**，agent 亦註明「唔係投資建議」。
