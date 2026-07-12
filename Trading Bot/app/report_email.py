from __future__ import annotations

import argparse
import base64
import logging
import mimetypes
import os
import smtplib
import zipfile
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

LOG = logging.getLogger("report_email")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _image_to_data_uri(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _resolve_chart_path(output_dir: Path, chart_path: str) -> Path | None:
    if not chart_path:
        return None
    candidate = Path(chart_path)
    if candidate.exists():
        return candidate
    relative = output_dir / Path(chart_path).name
    if relative.exists():
        return relative
    joined = output_dir.parent / chart_path
    if joined.exists():
        return joined
    nested = output_dir / chart_path.replace("../Cursor output/", "").replace("../Cursor output\\", "")
    if nested.exists():
        return nested
    return None


def _dataframe_to_html(frame: pd.DataFrame, empty_message: str) -> str:
    if frame.empty:
        return f"<p><em>{empty_message}</em></p>"
    display = frame.copy()
    for column in ("chart_path",):
        if column in display.columns:
            display[column] = display[column].apply(lambda value: Path(str(value)).name if value else "")
    return display.to_html(index=False, border=0, classes="data-table", escape=True)


def _chart_section(title: str, chart_paths: list[Path]) -> str:
    if not chart_paths:
        return f"<h2>{title}</h2><p><em>No charts available.</em></p>"
    blocks = [f"<h2>{title}</h2>"]
    for path in chart_paths:
        blocks.append(
            f'<div class="chart-card"><h3>{path.stem}</h3>'
            f'<img src="{_image_to_data_uri(path)}" alt="{path.name}" /></div>'
        )
    return "\n".join(blocks)


def generate_html_report(output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    report_dir = output_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    stock_df = _read_csv(output_dir / "us_stocks_candidates.csv")
    crypto_df = _read_csv(output_dir / "crypto_candidates.csv")
    crypto_summary_df = _read_csv(output_dir / "crypto_chart_summary.csv")
    crypto_alerts_df = _read_csv(output_dir / "crypto_alerts.csv")
    settings_text = _read_text(output_dir / "scan_settings.txt")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    stock_charts = sorted((output_dir / "us_stock_charts").glob("*.png")) if (output_dir / "us_stock_charts").exists() else []
    crypto_charts = sorted((output_dir / "crypto_charts").glob("*.png")) if (output_dir / "crypto_charts").exists() else []

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Market Scanner Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    h1, h2, h3 {{ color: #111827; }}
    .meta, .settings {{ background: #f3f4f6; padding: 12px 16px; border-radius: 8px; }}
    .data-table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
    .data-table th, .data-table td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; font-size: 14px; }}
    .data-table th {{ background: #e5e7eb; }}
    .chart-card {{ margin: 20px 0 32px; }}
    .chart-card img {{ max-width: 100%; border: 1px solid #d1d5db; border-radius: 8px; }}
    .disclaimer {{ margin-top: 32px; font-size: 13px; color: #6b7280; }}
  </style>
</head>
<body>
  <h1>Market Scanner Report</h1>
  <p class="meta"><strong>Generated:</strong> {generated_at}</p>
  <h2>Scan Settings</h2>
  <pre class="settings">{settings_text or "No scan settings file found."}</pre>

  <h2>US Stock Candidates</h2>
  {_dataframe_to_html(stock_df, "No US stock candidates matched the current filters.")}
  {_chart_section("US Stock Charts", stock_charts)}

  <h2>Crypto Candidates</h2>
  {_dataframe_to_html(crypto_df, "No crypto candidates matched the current filters.")}

  <h2>Crypto Technical Analysis</h2>
  {_dataframe_to_html(crypto_summary_df, "No crypto technical chart summaries were generated.")}
  {_dataframe_to_html(crypto_alerts_df, "No crypto alerts were triggered.")}
  {_chart_section("Crypto Charts", crypto_charts)}

  <p class="disclaimer">Not financial advice. This report is generated automatically for research and watchlist purposes only.</p>
</body>
</html>
"""
    report_path = report_dir / "market_scanner_report.html"
    report_path.write_text(html, encoding="utf-8")
    LOG.info("HTML report written to %s", report_path)
    return report_path


def create_report_zip(output_dir: Path, report_path: Path) -> Path:
    output_dir = output_dir.resolve()
    zip_path = output_dir / "report" / "market_scanner_report.zip"
    include_paths: list[Path] = [report_path]
    for pattern in (
        "us_stocks_candidates.csv",
        "crypto_candidates.csv",
        "crypto_chart_summary.csv",
        "crypto_alerts.csv",
        "scan_settings.txt",
    ):
        path = output_dir / pattern
        if path.exists():
            include_paths.append(path)
    for folder in ("us_stock_charts", "crypto_charts"):
        chart_dir = output_dir / folder
        if chart_dir.exists():
            include_paths.extend(sorted(chart_dir.glob("*.png")))

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in include_paths:
            archive.write(path, arcname=path.relative_to(output_dir))
    LOG.info("Report zip written to %s", zip_path)
    return zip_path


def _smtp_settings() -> tuple[str, int, str, str, str]:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    sender = os.getenv("EMAIL_FROM", user).strip() or user
    return host, port, user, password, sender


def send_report_email(
    to_email: str,
    report_path: Path,
    zip_path: Path,
    stock_count: int,
    crypto_count: int,
) -> None:
    host, port, user, password, sender = _smtp_settings()
    if not user or not password:
        raise RuntimeError(
            "SMTP credentials are not configured. Set SMTP_USER and SMTP_PASSWORD "
            "(Gmail users should use an app password)."
        )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"Market Scanner Report - {generated_at}"
    body = f"""Market Scanner Report

Generated: {generated_at}
US stock candidates: {stock_count}
Crypto candidates: {crypto_count}

The HTML report and a ZIP attachment with all CSV files and charts are included.

Not financial advice.
"""

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to_email
    message.set_content(body)

    html = report_path.read_text(encoding="utf-8")
    message.add_alternative(html, subtype="html")

    message.add_attachment(
        report_path.read_bytes(),
        maintype="text",
        subtype="html",
        filename=report_path.name,
    )
    message.add_attachment(
        zip_path.read_bytes(),
        maintype="application",
        subtype="zip",
        filename=zip_path.name,
    )

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(message)
    LOG.info("Report email sent to %s", to_email)


def build_and_send_report(output_dir: Path, to_email: str) -> tuple[Path, Path]:
    report_path = generate_html_report(output_dir)
    zip_path = create_report_zip(output_dir, report_path)
    stock_count = len(_read_csv(output_dir / "us_stocks_candidates.csv"))
    crypto_count = len(_read_csv(output_dir / "crypto_candidates.csv"))
    send_report_email(to_email, report_path, zip_path, stock_count, crypto_count)
    return report_path, zip_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and email the market scanner report.")
    parser.add_argument("--output-dir", default="platform_output", help="Scanner output directory.")
    parser.add_argument("--email", default="skwo671@gmail.com", help="Recipient email address.")
    parser.add_argument("--run-scan", action="store_true", help="Run platform scanner before generating the report.")
    parser.add_argument("--weekly-turnover-min", type=float, default=0.03)
    parser.add_argument("--crypto-deep-scan-limit", type=int, default=40)
    parser.add_argument("--stock-universe-size", type=int, default=500)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    output_dir = Path(args.output_dir)

    if args.run_scan:
        from .platform_scanner import main as run_platform_scan

        scan_args = [
            "platform_scanner",
            "--output-dir",
            str(output_dir),
            "--weekly-turnover-min",
            str(args.weekly_turnover_min),
            "--crypto-deep-scan-limit",
            str(args.crypto_deep_scan_limit),
            "--stock-universe-size",
            str(args.stock_universe_size),
        ]
        import sys

        previous_argv = sys.argv
        try:
            sys.argv = scan_args
            run_platform_scan()
        finally:
            sys.argv = previous_argv

    report_path = generate_html_report(output_dir)
    zip_path = create_report_zip(output_dir, report_path)
    stock_count = len(_read_csv(output_dir / "us_stocks_candidates.csv"))
    crypto_count = len(_read_csv(output_dir / "crypto_candidates.csv"))

    try:
        send_report_email(args.email, report_path, zip_path, stock_count, crypto_count)
        print(f"Report emailed to {args.email}")
    except Exception as exc:
        print(f"Report generated at {report_path}")
        print(f"Zip package generated at {zip_path}")
        print(f"Email was not sent: {exc}")
        print("Configure SMTP_USER and SMTP_PASSWORD in your environment to enable email delivery.")
        return 1

    print(f"Report: {report_path}")
    print(f"Zip: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
