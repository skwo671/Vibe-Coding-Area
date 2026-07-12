from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.asset_display import (
    AssetDisplayInfo,
    chart_filename_en,
    crypto_logo_url_from_symbol,
    format_chart_title,
    load_logo_image,
    load_logo_image_with_fallbacks,
    resolve_crypto_display,
    resolve_stock_display,
    stock_logo_url,
    stock_logo_urls,
)


class AssetDisplayTests(unittest.TestCase):
    def test_format_chart_title_uses_english_name(self) -> None:
        title = format_chart_title("AAPL", "Apple Inc.", "Daily Technical")
        self.assertIn("AAPL", title)
        self.assertIn("Apple Inc.", title)
        self.assertIn("Daily Technical", title)

    def test_chart_filename_en_uses_english_name(self) -> None:
        self.assertEqual(chart_filename_en("Visa Inc.", "V", "daily"), "Visa_Inc_daily.png")

    def test_chart_filename_en_falls_back_to_symbol(self) -> None:
        self.assertEqual(chart_filename_en("", "BTC", "technical"), "BTC_technical.png")

    def test_stock_logo_urls_includes_fallbacks(self) -> None:
        urls = stock_logo_urls("GEV")
        self.assertGreaterEqual(len(urls), 2)
        self.assertTrue(any("finnhub" in url for url in urls))
        self.assertTrue(any("companiesmarketcap" in url for url in urls))

    def test_stock_logo_url_uses_finnhub_pattern(self) -> None:
        self.assertIn("V.png", stock_logo_url("V"))

    def test_crypto_logo_url_from_symbol_strips_usd_suffix(self) -> None:
        url = crypto_logo_url_from_symbol("BTC-USD")
        self.assertIn("/btc.png", url)

    def test_load_logo_image_supports_png(self) -> None:
        image = load_logo_image("https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/V.png")
        self.assertIsNotNone(image)
        assert image is not None
        self.assertGreater(image.size, 0)

    def test_load_logo_image_with_fallbacks_uses_second_source(self) -> None:
        image = load_logo_image_with_fallbacks(
            [
                "https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/GEV.png",
                "https://companiesmarketcap.com/img/company-logos/256/GEV.png",
            ]
        )
        self.assertIsNotNone(image)

    def test_resolve_stock_display_uses_yfinance_english_name(self) -> None:
        display = resolve_stock_display("V", "V")
        self.assertIn("Visa", display.name_en)

    def test_resolve_crypto_display_uses_english_name(self) -> None:
        display = resolve_crypto_display("BTC", "Bitcoin", logo_url="https://example.com/btc.png")
        self.assertEqual(display.name_en, "Bitcoin")
        self.assertEqual(display.logo_url, "https://example.com/btc.png")

    def test_resolve_crypto_display_fetches_name_from_coingecko(self) -> None:
        client = MagicMock()
        client._get.return_value = {"localization": {"zh": "以太坊"}, "name": "Ethereum"}
        display = resolve_crypto_display("ETH", "Ethereum", coin_id="ethereum", coingecko_client=client)
        self.assertEqual(display.name_en, "Ethereum")


if __name__ == "__main__":
    unittest.main()
