from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import requests

STOCK_NAMES_ZH_PATH = Path(__file__).resolve().parent.parent / "data" / "stock_names_zh.json"
FINNHUB_LOGO_URL = "https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/{symbol}.png"
_CJK_FONT_CONFIGURED = False
_STOCK_ZH_CACHE: dict[str, str] | None = None
_CRYPTO_ZH_CACHE: dict[str, str] = {}


@dataclass(frozen=True)
class AssetDisplayInfo:
    symbol: str
    name_en: str
    name_zh: str
    logo_url: str


def configure_cjk_font() -> None:
    global _CJK_FONT_CONFIGURED
    if _CJK_FONT_CONFIGURED:
        return
    import matplotlib.pyplot as plt

    for font_name in ("WenQuanYi Micro Hei", "Noto Sans CJK SC", "SimHei", "Arial Unicode MS", "DejaVu Sans"):
        try:
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            _CJK_FONT_CONFIGURED = True
            return
        except Exception:
            continue
    _CJK_FONT_CONFIGURED = True


def load_stock_zh_names() -> dict[str, str]:
    global _STOCK_ZH_CACHE
    if _STOCK_ZH_CACHE is not None:
        return _STOCK_ZH_CACHE
    if STOCK_NAMES_ZH_PATH.exists():
        _STOCK_ZH_CACHE = {str(k).upper(): str(v) for k, v in json.loads(STOCK_NAMES_ZH_PATH.read_text(encoding="utf-8")).items()}
    else:
        _STOCK_ZH_CACHE = {}
    return _STOCK_ZH_CACHE


def stock_logo_url(symbol: str) -> str:
    return FINNHUB_LOGO_URL.format(symbol=symbol.upper().replace(".", "-"))


def crypto_logo_url_from_symbol(symbol: str) -> str:
    base = symbol.upper().replace("-USD", "").replace("-USDT", "")
    return f"https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/{base.lower()}.png"


def resolve_stock_display(symbol: str, name_en: str = "") -> AssetDisplayInfo:
    english_name = name_en or symbol
    chinese_name = load_stock_zh_names().get(symbol.upper(), "")
    if not chinese_name:
        try:
            import yfinance as yf

            info = yf.Ticker(symbol).get_info()
            english_name = str(info.get("longName") or info.get("shortName") or english_name)
        except Exception:
            pass
        chinese_name = english_name
    return AssetDisplayInfo(symbol=symbol, name_en=english_name, name_zh=chinese_name, logo_url=stock_logo_url(symbol))


def resolve_crypto_display(
    symbol: str,
    name_en: str,
    coin_id: str = "",
    logo_url: str = "",
    coingecko_client: object | None = None,
) -> AssetDisplayInfo:
    chinese_name = load_stock_zh_names().get(symbol.upper(), "")
    if not chinese_name and coin_id and coingecko_client is not None:
        chinese_name = fetch_crypto_zh_name(coingecko_client, coin_id)
    if not chinese_name:
        chinese_name = name_en or symbol
    return AssetDisplayInfo(
        symbol=symbol,
        name_en=name_en or symbol,
        name_zh=chinese_name,
        logo_url=logo_url,
    )


def fetch_crypto_zh_name(coingecko_client: object, coin_id: str) -> str:
    if coin_id in _CRYPTO_ZH_CACHE:
        return _CRYPTO_ZH_CACHE[coin_id]
    try:
        payload = coingecko_client._get(
            f"/coins/{coin_id}",
            {
                "localization": "true",
                "tickers": "false",
                "market_data": "false",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false",
            },
        )
        localization = payload.get("localization", {})
        chinese_name = localization.get("zh") or localization.get("zh-tw") or payload.get("name", coin_id)
    except Exception as exc:
        logging.getLogger("asset_display").warning("Failed to fetch Chinese name for %s: %s", coin_id, exc)
        chinese_name = coin_id
    _CRYPTO_ZH_CACHE[coin_id] = str(chinese_name)
    return _CRYPTO_ZH_CACHE[coin_id]


def format_chart_title(symbol: str, name_zh: str, name_en: str, suffix: str = "") -> str:
    zh = name_zh or symbol
    en = name_en or symbol
    if zh == en:
        title = f"{symbol} {zh}"
    else:
        title = f"{symbol} {zh}（{en}）"
    if suffix:
        title = f"{title} - {suffix}"
    return title


def add_logo_to_axes(ax, logo_url: str, zoom: float = 0.16) -> None:
    if not logo_url:
        return
    try:
        import matplotlib.pyplot as plt
        from matplotlib.offsetbox import AnnotationBbox, OffsetImage

        response = requests.get(logo_url, timeout=15)
        response.raise_for_status()
        image = plt.imread(BytesIO(response.content))
        image_box = OffsetImage(image, zoom=zoom)
        annotation = AnnotationBbox(
            image_box,
            (0.02, 0.98),
            xycoords="axes fraction",
            frameon=False,
            box_alignment=(0, 1),
            zorder=5,
        )
        ax.add_artist(annotation)
    except Exception as exc:
        logging.getLogger("asset_display").warning("Failed to load logo from %s: %s", logo_url, exc)
