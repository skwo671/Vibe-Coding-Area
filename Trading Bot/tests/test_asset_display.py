from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.asset_display import (
    AssetDisplayInfo,
    crypto_logo_url_from_symbol,
    format_chart_title,
    load_stock_zh_names,
    resolve_crypto_display,
    resolve_stock_display,
    stock_logo_url,
)


class AssetDisplayTests(unittest.TestCase):
    def test_load_stock_zh_names_contains_aapl(self) -> None:
        names = load_stock_zh_names()
        self.assertEqual(names["AAPL"], "苹果")

    def test_stock_logo_url_uses_finnhub_pattern(self) -> None:
        self.assertIn("AAPL.png", stock_logo_url("AAPL"))

    def test_crypto_logo_url_from_symbol_strips_usd_suffix(self) -> None:
        url = crypto_logo_url_from_symbol("BTC-USD")
        self.assertIn("/btc.png", url)

    def test_format_chart_title_with_chinese_and_english(self) -> None:
        title = format_chart_title("AAPL", "苹果", "Apple Inc.", "日線")
        self.assertIn("AAPL", title)
        self.assertIn("苹果", title)
        self.assertIn("Apple Inc.", title)
        self.assertIn("日線", title)

    def test_format_chart_title_same_zh_en(self) -> None:
        title = format_chart_title("XYZ", "XYZ", "XYZ")
        self.assertEqual(title, "XYZ XYZ")

    def test_resolve_stock_display_uses_mapping(self) -> None:
        display = resolve_stock_display("V", "Visa Inc.")
        self.assertEqual(display.name_zh, "维萨")
        self.assertIn("V.png", display.logo_url)

    def test_resolve_crypto_display_uses_mapping(self) -> None:
        display = resolve_crypto_display("BTC-USD", "Bitcoin", logo_url="https://example.com/btc.png")
        self.assertEqual(display.name_zh, "比特币")
        self.assertEqual(display.logo_url, "https://example.com/btc.png")

    def test_resolve_crypto_display_fetches_zh_from_coingecko(self) -> None:
        client = MagicMock()
        client._get.return_value = {"localization": {"zh": "以太坊"}, "name": "Ethereum"}
        display = resolve_crypto_display("ETH", "Ethereum", coin_id="ethereum", coingecko_client=client)
        self.assertEqual(display.name_zh, "以太坊")

    def test_resolve_crypto_display_falls_back_to_english_name(self) -> None:
        display = resolve_crypto_display("UNKNOWN", "Unknown Coin")
        self.assertEqual(display.name_zh, "Unknown Coin")


if __name__ == "__main__":
    unittest.main()
