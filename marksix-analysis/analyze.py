#!/usr/bin/env python3
"""Statistical analysis of public Mark Six draw history.

This script describes historical patterns only. Independent draws mean past
frequencies do not improve the chance of predicting future results.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from scipy import stats

ROOT = Path(__file__).resolve().parent
DATA_CSV = ROOT / "data" / "draws.csv"
OUTPUT_DIR = ROOT / "output"
BALL_MIN, BALL_MAX = 1, 49
N_MAIN = 6
# Mark Six expanded to 49 numbers on 2002-07-04; earlier eras bias low-frequency "cold" highs.
DEFAULT_SINCE = "2002-07-04"


def configure_font() -> str:
    candidates = [
        "WenQuanYi Micro Hei",
        "Noto Sans CJK TC",
        "Noto Sans CJK JP",
        "Droid Sans Fallback",
        "PingFang TC",
        "Microsoft JhengHei",
        "Arial Unicode MS",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return name
    return "DejaVu Sans"


def load_draws(path: Path, since: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run: python fetch_data.py"
        )
    full = pd.read_csv(path, parse_dates=["date"])
    needed = ["draw_id", "date", "n1", "n2", "n3", "n4", "n5", "n6", "special"]
    missing = [c for c in needed if c not in full.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    full = full.sort_values("date").reset_index(drop=True)
    if since:
        df = full[full["date"] >= pd.Timestamp(since)].copy().reset_index(drop=True)
        if df.empty:
            raise ValueError(f"No draws on/after {since}")
    else:
        df = full.copy()
    return full, df


def ball_matrix(df: pd.DataFrame) -> np.ndarray:
    return df[["n1", "n2", "n3", "n4", "n5", "n6"]].to_numpy(dtype=int)


def frequency_table(df: pd.DataFrame) -> pd.DataFrame:
    main = ball_matrix(df).ravel()
    main_counts = pd.Series(main).value_counts().reindex(
        range(BALL_MIN, BALL_MAX + 1), fill_value=0
    )
    special_counts = (
        df["special"].value_counts().reindex(range(BALL_MIN, BALL_MAX + 1), fill_value=0)
    )
    expected_main = len(df) * N_MAIN / BALL_MAX
    expected_special = len(df) / BALL_MAX

    out = pd.DataFrame(
        {
            "number": range(BALL_MIN, BALL_MAX + 1),
            "main_count": main_counts.to_numpy(),
            "special_count": special_counts.to_numpy(),
            "main_rate": main_counts.to_numpy() / len(df),
            "main_vs_expected": main_counts.to_numpy() - expected_main,
            "special_vs_expected": special_counts.to_numpy() - expected_special,
        }
    )
    return out


def gap_table(df: pd.DataFrame) -> pd.DataFrame:
    """Draws since each number last appeared as a main ball."""
    last_seen: dict[int, int] = {}
    rows = []
    mats = ball_matrix(df)
    for i, balls in enumerate(mats):
        for n in balls:
            last_seen[int(n)] = i
    latest = len(df) - 1
    for n in range(BALL_MIN, BALL_MAX + 1):
        if n in last_seen:
            gap = latest - last_seen[n]
            last_date = df.loc[last_seen[n], "date"]
        else:
            gap = len(df)
            last_date = pd.NaT
        rows.append({"number": n, "gap_draws": gap, "last_date": last_date})
    return pd.DataFrame(rows).sort_values("gap_draws", ascending=False)


def odd_even_sum_zone(df: pd.DataFrame) -> dict[str, pd.Series]:
    mats = ball_matrix(df)
    odd_counts = (mats % 2 == 1).sum(axis=1)
    sums = mats.sum(axis=1)
    zones = np.digitize(mats, bins=[16.5, 32.5], right=True)  # 0,1,2
    zone_counts = np.apply_along_axis(
        lambda row: np.bincount(row, minlength=3), 1, zones
    )
    return {
        "odd_count": pd.Series(odd_counts).value_counts().sort_index(),
        "sum": pd.Series(sums),
        "zone_low": pd.Series(zone_counts[:, 0]),
        "zone_mid": pd.Series(zone_counts[:, 1]),
        "zone_high": pd.Series(zone_counts[:, 2]),
    }


def consecutive_pairs(df: pd.DataFrame) -> pd.DataFrame:
    mats = np.sort(ball_matrix(df), axis=1)
    pair_counts: dict[tuple[int, int], int] = {}
    for row in mats:
        for a, b in zip(row, row[1:]):
            if b == a + 1:
                pair_counts[(int(a), int(b))] = pair_counts.get((int(a), int(b)), 0) + 1
    if not pair_counts:
        return pd.DataFrame(columns=["a", "b", "count"])
    rows = [{"a": a, "b": b, "count": c} for (a, b), c in pair_counts.items()]
    return pd.DataFrame(rows).sort_values("count", ascending=False)


def chi_square_uniform(freq: pd.DataFrame, n_draws: int) -> dict:
    observed = freq["main_count"].to_numpy(dtype=float)
    expected = np.full_like(observed, n_draws * N_MAIN / BALL_MAX)
    chi2, p = stats.chisquare(observed, expected)
    return {
        "chi2": float(chi2),
        "p_value": float(p),
        "df": int(BALL_MAX - 1),
        "expected_per_number": float(expected[0]),
        "interpretation": (
            "未能拒絕「各號碼出現次數均勻」假說（p ≥ 0.05）"
            if p >= 0.05
            else "拒絕均勻假說（p < 0.05）；仍可能只係抽樣波動，唔代表可預測未來"
        ),
    }


def runs_test_odd_even(df: pd.DataFrame) -> dict:
    """Wald–Wolfowitz-style runs test on whether draw-sum is above median."""
    sums = ball_matrix(df).sum(axis=1)
    median = np.median(sums)
    binary = (sums > median).astype(int)
    # Drop ties at median for a cleaner two-category series.
    mask = sums != median
    binary = binary[mask]
    if len(binary) < 20:
        return {"available": False}
    n1 = int((binary == 1).sum())
    n0 = int((binary == 0).sum())
    runs = 1 + int(np.sum(binary[1:] != binary[:-1]))
    mu = 1 + 2 * n1 * n0 / (n1 + n0)
    var = (
        2 * n1 * n0 * (2 * n1 * n0 - n1 - n0)
        / (((n1 + n0) ** 2) * (n1 + n0 - 1))
    )
    z = (runs - mu) / np.sqrt(var) if var > 0 else 0.0
    p = float(2 * (1 - stats.norm.cdf(abs(z))))
    return {
        "available": True,
        "runs": runs,
        "z": float(z),
        "p_value": p,
        "interpretation": (
            "高低和值序列未見明顯「一串熱、一串冷」結構（p ≥ 0.05）"
            if p >= 0.05
            else "高低和值序列出現非隨機式 runs（p < 0.05）；仍唔等於可預測下期號碼"
        ),
    }


def plot_frequency(freq: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(freq["number"], freq["main_count"], color="#1f4e79", width=0.8)
    expected = freq["main_count"].mean()
    ax.axhline(expected, color="#c45c26", linestyle="--", linewidth=1.5, label="期望次數")
    ax.set_title("正碼出現次數（全歷史）")
    ax.set_xlabel("號碼")
    ax.set_ylabel("次數")
    ax.set_xticks(range(1, 50, 2))
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def plot_gaps(gaps: pd.DataFrame, out: Path) -> None:
    top = gaps.head(15).sort_values("gap_draws")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(top["number"].astype(str), top["gap_draws"], color="#3d6b4f")
    ax.set_title("目前遺漏期數 Top 15（正碼）")
    ax.set_xlabel("距離上次出現嘅攪珠期數")
    ax.set_ylabel("號碼")
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def plot_sum_hist(sums: pd.Series, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(sums, bins=30, color="#5b4b8a", edgecolor="white")
    ax.axvline(sums.mean(), color="#c45c26", linestyle="--", label=f"平均 {sums.mean():.1f}")
    ax.set_title("六個正碼和值分布")
    ax.set_xlabel("和值")
    ax.set_ylabel("期數")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def plot_odd_even(odd_counts: pd.Series, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(odd_counts.index.astype(str), odd_counts.values, color="#8a4b3b")
    ax.set_title("每期奇數正碼個數分布")
    ax.set_xlabel("奇數個數（0–6）")
    ax.set_ylabel("期數")
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def build_report(
    full: pd.DataFrame,
    df: pd.DataFrame,
    since: str | None,
    freq: pd.DataFrame,
    gaps: pd.DataFrame,
    extras: dict,
    chi2: dict,
    runs: dict,
    pairs: pd.DataFrame,
) -> str:
    hot = freq.sort_values("main_count", ascending=False).head(10)
    cold = freq.sort_values("main_count", ascending=True).head(10)
    recent = df.tail(1).iloc[0]
    lines = [
        "# 香港六合彩公開開獎紀錄統計報告",
        "",
        "## 重要聲明",
        "",
        "- 本報告只做**歷史描述統計**，唔係預測下期攪珠結果。",
        "- 六合彩每期理論上獨立；冷熱號、遺漏值**唔代表**下期中獎率上升。",
        "- 官方結果以香港賽馬會公佈為準。",
        "",
        "## 數據概覽",
        "",
        f"- 原始檔期數：{len(full)}（{full['date'].min().date()} → {full['date'].max().date()}）",
        f"- 分析期數：{len(df)}（{df['date'].min().date()} → {df['date'].max().date()}）",
        (
            f"- 分析起點：{since}（現行 49 選 6；較早年代球數較少，"
            "若用全歷史會令 46–49「假性偏冷」）"
            if since
            else "- 分析起點：全歷史（注意球數規則曾多次擴大）"
        ),
        f"- 最新一期：{recent['draw_id']}（{recent['date'].date()}）"
        f" 正碼 {[int(recent[c]) for c in ['n1','n2','n3','n4','n5','n6']]}"
        f" 特別號碼 {int(recent['special'])}",
        f"- 數據來源欄：{df['source'].iloc[0] if 'source' in df.columns else 'n/a'}",
        "",
        "## 正碼頻率（熱號 / 冷號）",
        "",
        "理論上每個號碼作為正碼嘅期望次數約為 "
        f"{len(df) * N_MAIN / BALL_MAX:.1f} 次（{len(df)} 期 × 6 / 49）。",
        "",
        "### 出現最多 Top 10",
        "",
        "| 號碼 | 次數 | 相對期望 |",
        "| --- | ---: | ---: |",
    ]
    for _, r in hot.iterrows():
        lines.append(
            f"| {int(r['number'])} | {int(r['main_count'])} | {r['main_vs_expected']:+.1f} |"
        )

    lines += [
        "",
        "### 出現最少 Top 10",
        "",
        "| 號碼 | 次數 | 相對期望 |",
        "| --- | ---: | ---: |",
    ]
    for _, r in cold.iterrows():
        lines.append(
            f"| {int(r['number'])} | {int(r['main_count'])} | {r['main_vs_expected']:+.1f} |"
        )

    lines += [
        "",
        "## 目前遺漏（距離上次以正碼出現）",
        "",
        "| 號碼 | 遺漏期數 | 上次日期 |",
        "| --- | ---: | --- |",
    ]
    for _, r in gaps.head(10).iterrows():
        last = (
            r["last_date"].date().isoformat()
            if pd.notna(r["last_date"])
            else "—"
        )
        lines.append(f"| {int(r['number'])} | {int(r['gap_draws'])} | {last} |")

    odd = extras["odd_count"]
    sums = extras["sum"]
    lines += [
        "",
        "## 結構分布",
        "",
        f"- 六正碼和值：平均 {sums.mean():.2f}，中位數 {sums.median():.1f}，"
        f"標準差 {sums.std(ddof=1):.2f}",
        f"- 奇數個數最常見：{int(odd.idxmax())} 個奇數（{int(odd.max())} 期）",
        f"- 低區(1–16) / 中區(17–32) / 高區(33–49) 平均每期個數："
        f"{extras['zone_low'].mean():.2f} / "
        f"{extras['zone_mid'].mean():.2f} / "
        f"{extras['zone_high'].mean():.2f}",
        "",
        "## 連號對（相鄰兩個正碼，例如 12+13）",
        "",
    ]
    if pairs.empty:
        lines.append("無連號對紀錄。")
    else:
        lines += [
            "| 連號 | 出現期數 |",
            "| --- | ---: |",
        ]
        for _, r in pairs.head(10).iterrows():
            lines.append(f"| {int(r['a'])}-{int(r['b'])} | {int(r['count'])} |")

    lines += [
        "",
        "## 隨機性檢驗（描述用途）",
        "",
        "### χ² 均勻性檢驗（正碼頻率）",
        "",
        f"- χ² = {chi2['chi2']:.2f}（自由度 {chi2['df']}）",
        f"- p-value = {chi2['p_value']:.4g}",
        f"- {chi2['interpretation']}",
        "",
        "### Runs 檢驗（和值高於／低於中位數）",
        "",
    ]
    if runs.get("available"):
        lines += [
            f"- runs = {runs['runs']}，z = {runs['z']:.3f}，p = {runs['p_value']:.4g}",
            f"- {runs['interpretation']}",
        ]
    else:
        lines.append("- 樣本不足以計算。")

    lines += [
        "",
        "## 點樣解讀先正確",
        "",
        "1. 「熱號」只係過去出現得多，**下期機會唔因此變高**。",
        "2. 「遺漏好耐」亦唔等於「補號」；獨立事件冇記憶。",
        "3. χ² / runs 只係檢查歷史序列有冇明顯偏離簡單隨機模型，"
        "**唔係選號算法**。",
        "4. 若要娛樂選號，用真正隨機（例如 `secrets.SystemRandom`）已足夠。",
        "",
        "---",
        f"圖表輸出目錄：`{OUTPUT_DIR.as_posix()}`",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze Mark Six public history")
    parser.add_argument("--csv", type=Path, default=DATA_CSV)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--since",
        default=DEFAULT_SINCE,
        help=(
            f"Only analyze draws on/after this date (default {DEFAULT_SINCE}, "
            "49-ball era). Use empty string for full history."
        ),
    )
    args = parser.parse_args(argv)
    since = args.since.strip() or None

    font = configure_font()
    full, df = load_draws(args.csv, since=since)
    args.output.mkdir(parents=True, exist_ok=True)

    freq = frequency_table(df)
    gaps = gap_table(df)
    extras = odd_even_sum_zone(df)
    pairs = consecutive_pairs(df)
    chi2 = chi_square_uniform(freq, len(df))
    runs = runs_test_odd_even(df)

    freq.to_csv(args.output / "frequency.csv", index=False)
    gaps.to_csv(args.output / "gaps.csv", index=False)
    pairs.to_csv(args.output / "consecutive_pairs.csv", index=False)

    plot_frequency(freq, args.output / "frequency.png")
    plot_gaps(gaps, args.output / "gaps_top15.png")
    plot_sum_hist(extras["sum"], args.output / "sum_hist.png")
    plot_odd_even(extras["odd_count"], args.output / "odd_even.png")

    report = build_report(full, df, since, freq, gaps, extras, chi2, runs, pairs)
    report_path = args.output / "report.md"
    report_path.write_text(report, encoding="utf-8")

    summary = {
        "draws_full": int(len(full)),
        "draws_analyzed": int(len(df)),
        "since": since,
        "date_min": df["date"].min().date().isoformat(),
        "date_max": df["date"].max().date().isoformat(),
        "chi_square": chi2,
        "runs_test": runs,
        "font_used": font,
        "artifacts": [
            "frequency.csv",
            "gaps.csv",
            "consecutive_pairs.csv",
            "frequency.png",
            "gaps_top15.png",
            "sum_hist.png",
            "odd_even.png",
            "report.md",
        ],
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(report)
    print(f"\nWrote report → {report_path}")
    print(f"Charts / tables → {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
