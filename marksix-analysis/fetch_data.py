#!/usr/bin/env python3
"""Download public Hong Kong Mark Six draw history.

Primary source: community mirror of HKJC results
(https://github.com/icelam/mark-six-data-visualization), which scrapes
HKJC getJSON.aspx and is updated by GitHub Actions.

Optional: try HKJC getJSON.aspx directly when reachable (often blocked
outside HK / without browser cookies).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

GITHUB_ALL_JSON = (
    "https://raw.githubusercontent.com/icelam/"
    "mark-six-data-visualization/master/data/all.json"
)
HKJC_JSON = "https://bet2.hkjc.com/marksix/getJSON.aspx/"

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; MarkSixAnalysis/1.0; "
                "+https://github.com/icelam/mark-six-data-visualization)"
            ),
            "Accept": "application/json,text/plain,*/*",
        }
    )
    return s


def fetch_github_mirror(session: requests.Session) -> list[dict]:
    resp = session.get(GITHUB_ALL_JSON, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or not data:
        raise ValueError("GitHub mirror returned empty or unexpected payload")
    return data


def fetch_hkjc_quarter(
    session: requests.Session, start: date, end: date
) -> list[dict] | None:
    params = {
        "sd": start.strftime("%Y%m%d"),
        "ed": end.strftime("%Y%m%d"),
        "sb": "0",
    }
    try:
        resp = session.get(HKJC_JSON, params=params, timeout=30)
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "")
        if "html" in ctype.lower() or resp.text.lstrip().startswith("<"):
            return None
        data = resp.json()
        if not isinstance(data, list):
            return None
        return data
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        return None


def normalize_records(records: list[dict], source: str) -> pd.DataFrame:
    rows: list[dict] = []
    for item in records:
        nums = item.get("no")
        if isinstance(nums, str):
            nums = [n for n in nums.replace(" ", "").split("+") if n]
        if not nums or len(nums) != 6:
            continue

        draw_date = item.get("date")
        if isinstance(draw_date, str) and "/" in draw_date:
            # HKJC raw format: DD/MM/YYYY
            day, month, year = draw_date.split("/")
            draw_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        balls = [int(n) for n in nums]
        special = int(item["sno"]) if item.get("sno") not in (None, "") else None
        draw_id = str(item.get("id", "")).strip()
        rows.append(
            {
                "draw_id": draw_id,
                "date": draw_date,
                "n1": balls[0],
                "n2": balls[1],
                "n3": balls[2],
                "n4": balls[3],
                "n5": balls[4],
                "n6": balls[5],
                "special": special,
                "source": source,
            }
        )

    if not rows:
        raise ValueError("No valid draw records after normalization")

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    for col in ("n1", "n2", "n3", "n4", "n5", "n6", "special"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    df = df.dropna(subset=["n1", "n2", "n3", "n4", "n5", "n6", "special"])
    for col in ("n1", "n2", "n3", "n4", "n5", "n6", "special"):
        df[col] = df[col].astype(int)

    # Keep ascending draw order; drop duplicate draw_id keeping newest source row.
    df = df.sort_values(["date", "draw_id"]).drop_duplicates(
        subset=["draw_id"], keep="last"
    )
    df = df.reset_index(drop=True)
    return df


def save_frames(df: pd.DataFrame, source: str) -> tuple[Path, Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    json_path = RAW_DIR / "all_draws.json"
    csv_path = DATA_DIR / "draws.csv"

    payload = {
        "source": source,
        "fetched_on": date.today().isoformat(),
        "draw_count": int(len(df)),
        "date_min": df["date"].min().date().isoformat(),
        "date_max": df["date"].max().date().isoformat(),
        "records": json.loads(
            df.assign(date=df["date"].dt.strftime("%Y-%m-%d")).to_json(
                orient="records", force_ascii=False
            )
        ),
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    df.to_csv(csv_path, index=False)
    return csv_path, json_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Mark Six public draw history")
    parser.add_argument(
        "--prefer-hkjc",
        action="store_true",
        help="Try HKJC getJSON first (may fail outside HKJC network)",
    )
    args = parser.parse_args(argv)

    session = _session()
    records: list[dict] | None = None
    source = ""

    if args.prefer_hkjc:
        print("Trying HKJC getJSON.aspx for recent quarters...")
        # Pull a few recent years; fall back if blocked.
        chunks: list[dict] = []
        for year in range(date.today().year - 1, date.today().year + 1):
            quarters = [
                (date(year, 1, 1), date(year, 3, 31)),
                (date(year, 4, 1), date(year, 6, 30)),
                (date(year, 7, 1), date(year, 9, 30)),
                (date(year, 10, 1), date(year, 12, 31)),
            ]
            for start, end in quarters:
                if start > date.today():
                    continue
                end = min(end, date.today())
                part = fetch_hkjc_quarter(session, start, end)
                if part is None:
                    chunks = []
                    break
                chunks.extend(part)
            if not chunks and year == date.today().year - 1:
                break
        if chunks:
            records = chunks
            source = "hkjc_getJSON"

    if records is None:
        print(f"Downloading GitHub mirror:\n  {GITHUB_ALL_JSON}")
        records = fetch_github_mirror(session)
        source = "github:icelam/mark-six-data-visualization"

    df = normalize_records(records, source=source)
    csv_path, json_path = save_frames(df, source=source)

    print(
        f"Saved {len(df)} draws ({df['date'].min().date()} → {df['date'].max().date()})"
    )
    print(f"  CSV : {csv_path}")
    print(f"  JSON: {json_path}")
    print(f"  Source: {source}")
    print(
        "\nNote: Official results are published by HKJC. "
        "This dataset is for statistical analysis only."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
