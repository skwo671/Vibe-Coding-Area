#!/usr/bin/env python3
"""Send a WhatsApp Cloud API text or template message (official Meta Graph API only)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require_env(*names: str) -> dict[str, str]:
    missing = [n for n in names if not os.environ.get(n, "").strip()]
    if missing:
        print(
            "Missing credentials: " + ", ".join(missing) + f"\nCopy {ENV_PATH.name}.example to .env and fill values from Meta API Setup.",
            file=sys.stderr,
        )
        sys.exit(2)
    return {n: os.environ[n].strip() for n in names}


def graph_post(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"WhatsApp API HTTP {exc.code}: {detail}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a message via WhatsApp Cloud API")
    parser.add_argument("--file", type=Path, help="UTF-8 text file (daily report)")
    parser.add_argument("--text", help="Message body (overrides --file)")
    parser.add_argument(
        "--template",
        action="store_true",
        help="Send the configured template instead of free text",
    )
    args = parser.parse_args()
    load_env(ENV_PATH)
    creds = require_env("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_TO")
    version = os.environ.get("WHATSAPP_API_VERSION", "v21.0").strip()
    url = f"https://graph.facebook.com/{version}/{creds['WHATSAPP_PHONE_NUMBER_ID']}/messages"

    if args.template:
        payload = {
            "messaging_product": "whatsapp",
            "to": creds["WHATSAPP_TO"],
            "type": "template",
            "template": {
                "name": os.environ.get("WHATSAPP_TEMPLATE_NAME", "hello_world").strip(),
                "language": {"code": os.environ.get("WHATSAPP_TEMPLATE_LANG", "en_US").strip()},
            },
        }
    else:
        if args.text:
            body = args.text
        elif args.file:
            body = args.file.read_text(encoding="utf-8").strip()
        else:
            parser.error("Provide --text, --file, or --template")
        if len(body) > 4096:
            raise SystemExit("Message exceeds WhatsApp 4096 character limit")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": creds["WHATSAPP_TO"],
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }

    result = graph_post(url, creds["WHATSAPP_ACCESS_TOKEN"], payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
