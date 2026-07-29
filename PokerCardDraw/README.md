# 撲克牌抽牌 (PokerCardDraw)

一個用 SwiftUI 開發的 iOS 撲克牌抽牌 App，支援洗牌、逐張抽牌、一次抽多張，以及重置牌組。

## 功能

- 標準 52 張撲克牌
- 抽一張牌
- 一次抽 2 張或 5 張（適合簡單牌局練習）
- 洗牌與重置牌組
- 顯示剩餘牌數與已抽牌記錄
- 牌面動畫與賭桌風格介面

## 系統需求

- macOS（用於開發）
- Xcode 15 或以上
- iOS 17.0 或以上
- Apple Developer 帳號（若要安裝到真機或上架 App Store）

## 如何開啟專案

1. 將整個 `PokerCardDraw` 資料夾複製到你的 Mac
2. 用 Xcode 開啟 `PokerCardDraw.xcodeproj`
3. 在 Xcode 頂部選擇模擬器（例如 iPhone 15）或已連接的 iPhone
4. 按 `Cmd + R` 執行

## 專案結構

```
PokerCardDraw/
├── PokerCardDraw.xcodeproj
└── PokerCardDraw/
    ├── PokerCardDrawApp.swift      # App 入口
    ├── Models/
    │   ├── Card.swift              # 撲克牌模型
    │   └── Deck.swift              # 牌組邏輯
    ├── ViewModels/
    │   └── DeckViewModel.swift     # 狀態管理
    ├── Views/
    │   ├── ContentView.swift       # 主畫面
    │   └── CardView.swift          # 單張牌 UI
    └── Assets.xcassets
```

## 安裝到真機

1. 用 USB 連接 iPhone 到 Mac
2. 在 Xcode 選擇你的裝置
3. 到 **Signing & Capabilities**，選擇你的 Team
4. 將 `PRODUCT_BUNDLE_IDENTIFIER` 改成你獨有的 Bundle ID（例如 `com.yourname.PokerCardDraw`）
5. 按 `Cmd + R` 安裝

## 上架 App Store（可選）

1. 在 [App Store Connect](https://appstoreconnect.apple.com/) 建立新 App
2. 準備 App 圖示（1024×1024）及截圖
3. 在 Xcode 選擇 **Product → Archive**
4. 透過 Organizer 上傳到 App Store Connect
5. 填寫審核資料並提交

## 之後可擴充的功能

- 加入大小王
- 多副牌混合
- 德州撲克／二十一點等遊戲模式
- 音效與翻牌動畫
- 分享抽牌結果

## 授權

此專案供個人學習與使用。
