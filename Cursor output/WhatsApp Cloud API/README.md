# WhatsApp Cloud API 設定（2026-09-19）

試過喺呢個 Cloud Agent 瀏覽器開官方 Meta 開發者後台。**卡喺 Facebook 登入**，呢台機冇你嘅 Meta session，亦唔會叫你喺 chat 貼密碼。Gmail 都搵唔到現成 WhatsApp Business／Cloud API 帳號郵件。

官方文件：[WhatsApp Cloud API Get Started](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started)

## 你要喺自己部機完成嘅步驟

1. 用 Facebook 登入 [developers.facebook.com/apps](https://developers.facebook.com/apps)
2. Create app → 加 **WhatsApp** product
3. 喺 **API Setup** 複製：
   - Temporary access token
   - Phone number ID
   - 測試商業號碼
4. Add phone number：加你私人 WhatsApp（國際格式，例如 `8529xxxxxxx`）
5. 先 send 一次 **hello_world** template（新聯絡人必須用已審批 template）
6. 你用 WhatsApp 回一句之後，24 小時內先可以用自由文字發倉位報告

## 本地／Cloud Agent 點用

Repo 入面：`WhatsApp Cloud API/`

```bash
cd "WhatsApp Cloud API"
cp .env.example .env
# 填 WHATSAPP_ACCESS_TOKEN、WHATSAPP_PHONE_NUMBER_ID、WHATSAPP_TO
python3 send_report.py --template
python3 send_report.py --file "../Cursor output/報告/每日持倉盈虧_2026-09-19_HKT.md"
```

`.env` 唔好 commit。Token 過期就要返 Meta 後台再產生。

## 限制

- 呢個係**商業號碼**發俾你，唔係你私人 WhatsApp 當 bot。
- 日報排程要麼用已審批 template，要麼你每日先回商業號再開 session。
- 未填 `.env` 之前，`send_report.py` 只會報缺 credentials（已驗證）。
