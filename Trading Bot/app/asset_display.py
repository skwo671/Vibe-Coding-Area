from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import requests

STOCK_NAMES_ZH_PATH = Path(__file__).resolve().parent.parent / "data" / "stock_names_zh.json"
FINNHUB_LOGO_URL = "https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/{symbol}.png"
MARKET_CAP_LOGO_URL = "https://companiesmarketcap.com/img/company-logos/256/{symbol}.png"
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


def stock_logo_urls(symbol: str) -> list[str]:
    normalized = symbol.upper().replace(".", "-")
    compact = normalized.replace("-", "")
    return [
        FINNHUB_LOGO_URL.format(symbol=normalized),
        MARKET_CAP_LOGO_URL.format(symbol=compact),
        FINNHUB_LOGO_URL.format(symbol=symbol.upper()),
    ]


def crypto_logo_urls(symbol: str, coingecko_url: str = "") -> list[str]:
    urls: list[str] = []
    if coingecko_url:
        urls.append(coingecko_url)
    fallback = crypto_logo_url_from_symbol(symbol)
    if fallback not in urls:
        urls.append(fallback)
    return urls


def stock_logo_url(symbol: str) -> str:
    return stock_logo_urls(symbol)[0]


def crypto_logo_url_from_symbol(symbol: str) -> str:
    base = symbol.upper().replace("-USD", "").replace("-USDT", "")
    return f"https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/{base.lower()}.png"


def resolve_stock_display(symbol: str, name_en: str = "") -> AssetDisplayInfo:
    english_name = name_en or symbol
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).get_info()
        english_name = str(info.get("longName") or info.get("shortName") or english_name)
    except Exception:
        pass
    chinese_name = load_stock_zh_names().get(symbol.upper(), english_name)
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


def format_chart_title(symbol: str, name_en: str, suffix: str = "") -> str:
    name = name_en or symbol
    title = f"{symbol} {name}"
    if suffix:
        title = f"{title} - {suffix}"
    return title


def chart_filename_en(name_en: str, symbol: str, chart_type: str) -> str:
    base = (name_en or symbol).strip()
    safe = re.sub(r'[\\/:*?"<>|,]+', "", base)
    safe = re.sub(r"\s+", "_", safe).strip("._")
    if not safe:
        safe = symbol.replace(".", "_").replace("-", "_")
    return f"{safe}_{chart_type}.png"


def placeholder_logo_image(symbol: str) -> np.ndarray:
    from PIL import Image, ImageDraw

    size = 128
    image = Image.new("RGBA", (size, size), (236, 240, 245, 255))
    draw = ImageDraw.Draw(image)
    label = symbol.upper().replace("-USD", "").replace("-", "")[:4]
    draw.rectangle((8, 8, size - 8, size - 8), outline=(120, 130, 150, 255), width=3)
    draw.text((24, 48), label, fill=(60, 70, 90, 255))
    return np.asarray(image)


def load_logo_image_with_fallbacks(logo_urls: str | list[str]) -> np.ndarray | None:
    candidates = [logo_urls] if isinstance(logo_urls, str) else list(logo_urls)
    for url in candidates:
        if not url:
            continue
        image = _load_logo_image_quiet(url)
        if image is not None:
            return image
    return None


def _load_logo_image_quiet(logo_url: str) -> np.ndarray | None:
    try:
        from PIL import Image

        response = requests.get(logo_url, timeout=15, headers={"User-Agent": "MarketScanner/1.0"})
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")
        return np.asarray(image)
    except Exception:
        return None


def load_logo_image(logo_url: str) -> np.ndarray | None:
    image = _load_logo_image_quiet(logo_url)
    if image is None and logo_url:
        logging.getLogger("asset_display").warning("Failed to load logo from %s", logo_url)
    return image


def add_logo_to_axes(
    ax,
    symbol: str,
    asset_type: str = "stock",
    logo_url: str = "",
    zoom: float = 0.2,
) -> None:
    if asset_type == "crypto":
        candidates = crypto_logo_urls(symbol, logo_url)
    else:
        candidates = stock_logo_urls(symbol)

    image = load_logo_image_with_fallbacks(candidates)
    if image is None:
        logging.getLogger("asset_display").warning("Using placeholder logo for %s", symbol)
        image = placeholder_logo_image(symbol)
    try:
        from matplotlib.offsetbox import AnnotationBbox, OffsetImage

        image_box = OffsetImage(image, zoom=zoom)
        annotation = AnnotationBbox(
            image_box,
            (0.02, 0.98),
            xycoords="axes fraction",
            frameon=True,
            pad=0.15,
            bboxprops={"facecolor": "white", "edgecolor": "none", "alpha": 0.9},
            box_alignment=(0, 1),
            zorder=1000,
        )
        annotation.set_clip_on(False)
        ax.add_artist(annotation)
    except Exception as exc:
        logging.getLogger("asset_display").warning("Failed to place logo from %s: %s", logo_url, exc)
