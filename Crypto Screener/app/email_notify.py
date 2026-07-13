from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from .screener import ScreenResult


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    from_addr: str


def load_email_config() -> EmailConfig:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", user)

    if not user or not password:
        raise ValueError(
            "Missing SMTP credentials. Set SMTP_USER and SMTP_PASSWORD in .env "
            "(Gmail users need an App Password: https://myaccount.google.com/apppasswords)"
        )
    return EmailConfig(
        smtp_host=host,
        smtp_port=port,
        smtp_user=user,
        smtp_password=password,
        from_addr=from_addr,
    )


def _format_market_cap(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    return f"${value / 1_000_000:.0f}M"


def _build_html(results: List[ScreenResult], criteria_lines: List[str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not results:
        rows_html = "<tr><td colspan='8'>No coins matched all criteria.</td></tr>"
    else:
        rows_html = ""
        for i, r in enumerate(results, 1):
            rows_html += f"""
            <tr>
              <td>{i}</td>
              <td><strong>{r.symbol}</strong></td>
              <td>{r.name}</td>
              <td>${r.price_usd:,.4f}</td>
              <td>{_format_market_cap(r.market_cap_usd)}</td>
              <td>{r.days_since_52w_high}d ago</td>
              <td>+{r.pct_above_ma50:.1f}%</td>
              <td>{r.score:.1f}</td>
            </tr>"""

    criteria = "".join(f"<li>{line}</li>" for line in criteria_lines)
    return f"""
    <html><body style="font-family: sans-serif; color: #222;">
      <h2>Crypto Screener Report</h2>
      <p>Generated: {now}</p>
      <h3>Criteria</h3>
      <ul>{criteria}</ul>
      <h3>Results ({len(results)} coin(s))</h3>
      <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
        <tr style="background:#f0f0f0;">
          <th>#</th><th>Symbol</th><th>Name</th><th>Price</th>
          <th>Market Cap</th><th>52W High</th><th>Above MA50</th><th>Score</th>
        </tr>
        {rows_html}
      </table>
      <p style="color:#888; font-size:12px; margin-top:24px;">
        Data: CoinGecko + Binance. Not financial advice.
      </p>
    </body></html>
    """


def _build_plain(results: List[ScreenResult], criteria_lines: List[str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["Crypto Screener Report", f"Generated: {now}", "", "Criteria:"]
    lines.extend(f"  - {c}" for c in criteria_lines)
    lines.append("")

    if not results:
        lines.append("No coins matched all criteria.")
    else:
        lines.append(f"Results ({len(results)} coin(s)):")
        for i, r in enumerate(results, 1):
            lines.append(
                f"{i}. {r.symbol} ({r.name}) | ${r.price_usd:,.4f} | "
                f"{_format_market_cap(r.market_cap_usd)} | "
                f"52W high {r.days_since_52w_high}d ago | "
                f"+{r.pct_above_ma50:.1f}% above MA50 | Score {r.score:.1f}"
            )
    return "\n".join(lines)


def send_report(
    to_addr: str,
    results: List[ScreenResult],
    criteria_lines: List[str],
    config: Optional[EmailConfig] = None,
) -> None:
    cfg = config or load_email_config()
    subject = f"Crypto Screener: {len(results)} coin(s) found"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.from_addr
    msg["To"] = to_addr

    plain = _build_plain(results, criteria_lines)
    html = _build_html(results, criteria_lines)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(cfg.smtp_user, cfg.smtp_password)
        server.sendmail(cfg.from_addr, [to_addr], msg.as_string())
