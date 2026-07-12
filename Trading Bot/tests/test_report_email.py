from __future__ import annotations

import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from app.report_email import create_report_zip, generate_html_report


class ReportEmailTests(unittest.TestCase):
    def test_generate_html_report_includes_tables_and_charts(self) -> None:
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            pd.DataFrame({"symbol": ["V"], "latest_price": [100.0]}).to_csv(
                output_dir / "us_stocks_candidates.csv",
                index=False,
            )
            pd.DataFrame().to_csv(output_dir / "crypto_candidates.csv", index=False)
            pd.DataFrame().to_csv(output_dir / "crypto_chart_summary.csv", index=False)
            pd.DataFrame().to_csv(output_dir / "crypto_alerts.csv", index=False)
            (output_dir / "scan_settings.txt").write_text("Timeframe: daily", encoding="utf-8")
            chart_dir = output_dir / "us_stock_charts"
            chart_dir.mkdir()
            chart_path = chart_dir / "Visa_Inc_daily.png"
            chart_path.write_bytes(b"fakepng")

            report_path = generate_html_report(output_dir)
            html = report_path.read_text(encoding="utf-8")
            self.assertIn("Market Scanner Report", html)
            self.assertIn("US Stock Candidates", html)
            self.assertIn("Visa_Inc_daily", html)
            self.assertIn("data:image/png;base64,", html)

    def test_create_report_zip_contains_report_and_csv(self) -> None:
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            report_dir = output_dir / "report"
            report_dir.mkdir(parents=True)
            report_path = report_dir / "market_scanner_report.html"
            report_path.write_text("<html></html>", encoding="utf-8")
            (output_dir / "scan_settings.txt").write_text("settings", encoding="utf-8")

            zip_path = create_report_zip(output_dir, report_path)
            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
            self.assertIn("report/market_scanner_report.html", names)
            self.assertIn("scan_settings.txt", names)


if __name__ == "__main__":
    unittest.main()
