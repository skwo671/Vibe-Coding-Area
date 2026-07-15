"""Optional AI vision helper for Archroma color-card naming.

Enabled via AI設定.txt or env:
  PVH_AI_ENABLED=1
  PVH_AI_API_KEY=...
  PVH_AI_BASE_URL=https://api.openai.com/v1   (optional)
  PVH_AI_MODEL=gpt-4o-mini                    (optional)
  PVH_AI_MODE=fallback|always                 (optional)
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2

from pvh_filename.runtime import portable_root
from pvh_filename.simple_labels import normalize_token
from pvh_filename.simple_ocr import ARCHROMA_CODE_RE, CWF_LABEL_RE

CONFIG_NAMES = ("AI設定.txt", "ai_config.txt", "AI_CONFIG.txt")


@dataclass(frozen=True)
class AIColorConfig:
    enabled: bool = False
    mode: str = "fallback"  # fallback | always | off
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    source: str = ""

    @property
    def usable(self) -> bool:
        return bool(self.enabled and self.api_key and self.mode != "off")


@dataclass(frozen=True)
class AIColorResult:
    color_code: str = ""
    color_name: str = ""
    has_cwf_label: bool = False
    light_source: str = "D65"
    note: str = ""


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "啟用", "開啟"}


def _parse_config_text(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip().lower()] = value.strip()
    return data


def _load_config_file(path: Path) -> dict[str, str]:
    try:
        return _parse_config_text(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def find_ai_config_path(folder: Path | None = None) -> Path | None:
    search: list[Path] = []
    if folder is not None:
        search.append(folder.resolve())
        search.append(folder.resolve().parent)
    search.append(portable_root())
    search.append(Path.cwd())
    for base in search:
        for name in CONFIG_NAMES:
            path = base / name
            if path.is_file():
                return path
    return None


def load_ai_config(folder: Path | None = None) -> AIColorConfig:
    file_data: dict[str, str] = {}
    source = ""
    cfg_path = find_ai_config_path(folder)
    if cfg_path is not None:
        file_data = _load_config_file(cfg_path)
        source = str(cfg_path)

    enabled_raw = os.environ.get("PVH_AI_ENABLED") or file_data.get("enabled", "0")
    mode = (os.environ.get("PVH_AI_MODE") or file_data.get("mode") or "fallback").strip().lower()
    if mode in {"1", "true", "yes", "on"}:
        mode = "always"
    if mode in {"0", "false", "no", "off", "none"}:
        mode = "off"
    if mode not in {"fallback", "always", "off"}:
        mode = "fallback"

    api_key = (
        os.environ.get("PVH_AI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or file_data.get("api_key")
        or file_data.get("openai_api_key")
        or ""
    ).strip()
    base_url = (
        os.environ.get("PVH_AI_BASE_URL")
        or file_data.get("base_url")
        or "https://api.openai.com/v1"
    ).strip().rstrip("/")
    model = (
        os.environ.get("PVH_AI_MODEL") or file_data.get("model") or "gpt-4o-mini"
    ).strip()

    enabled = _parse_bool(str(enabled_raw)) and mode != "off" and bool(api_key)
    return AIColorConfig(
        enabled=enabled,
        mode=mode if enabled else "off",
        api_key=api_key,
        base_url=base_url,
        model=model,
        source=source,
    )


def ai_status_message(cfg: AIColorConfig | None = None) -> str:
    cfg = cfg or load_ai_config()
    if not cfg.usable:
        return "AI 色名: 未啟用（可設 AI設定.txt 或 PVH_AI_API_KEY）"
    where = f" / {Path(cfg.source).name}" if cfg.source else ""
    return f"AI 色名: 已啟用 ({cfg.mode}, {cfg.model}{where})"


def _image_to_data_url(path: Path, max_side: int = 1280) -> str | None:
    image = cv2.imread(str(path))
    if image is None:
        return None
    h, w = image.shape[:2]
    scale = min(1.0, max_side / max(h, w, 1))
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _extract_json_object(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_ai_name(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"null", "none", "n/a", "-"}:
        return ""
    return normalize_token(text)


def _normalize_ai_code(value: object) -> str:
    text = str(value or "").strip().upper()
    if not text or text.lower() in {"null", "none", "n/a", "-"}:
        return ""
    match = ARCHROMA_CODE_RE.search(text.replace("–", "-").replace("—", "-"))
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    digits = re.sub(r"\D", "", text)
    if len(digits) == 6:
        return f"{digits[:3]}-{digits[3:]}"
    return text


def _parse_ai_payload(data: dict) -> AIColorResult:
    code = _normalize_ai_code(data.get("color_code") or data.get("code") or "")
    name = _normalize_ai_name(data.get("color_name") or data.get("name") or "")
    cwf_raw = data.get("has_cwf_label", data.get("cwf", False))
    if isinstance(cwf_raw, str):
        has_cwf = _parse_bool(cwf_raw) or bool(CWF_LABEL_RE.search(cwf_raw))
    else:
        has_cwf = bool(cwf_raw)
    light = "CWF" if has_cwf else "D65"
    note = str(data.get("note") or data.get("reason") or "").strip()
    return AIColorResult(
        color_code=code,
        color_name=name,
        has_cwf_label=has_cwf,
        light_source=light,
        note=note,
    )


def read_color_card_with_ai(
    path: Path,
    cfg: AIColorConfig,
    *,
    hint_text: str = "",
    master_names: list[str] | None = None,
    timeout_sec: float = 45.0,
) -> AIColorResult | None:
    """Ask a vision LLM to read Archroma color name / code / CWF."""
    if not cfg.usable:
        return None

    data_url = _image_to_data_url(path)
    if not data_url:
        return None

    names = [n for n in (master_names or []) if n][:60]
    name_hint = ""
    if names:
        name_hint = "Known color names (prefer exact match if possible):\n" + ", ".join(names)

    prompt = (
        "You are helping rename Tommy Hilfiger / Archroma fabric color swatch photos.\n"
        "Look at the Archroma white header card and any CWF sticker.\n"
        "Return ONLY one JSON object with keys:\n"
        '  color_code: string like "654-920" (empty if unknown)\n'
        '  color_name: string like "DESERT SKY" (empty if unknown)\n'
        "  has_cwf_label: boolean (true only if a CWF label/sticker is visible)\n"
        "  note: short reason\n"
        "Rules:\n"
        "- Prefer the printed Archroma code ###-### on the card.\n"
        "- Prefer the official color name printed above the code.\n"
        "- has_cwf_label is true only if CWF appears as a label/sticker, not just generic text.\n"
        "- If unsure, leave fields empty rather than guessing wild values.\n"
    )
    if hint_text:
        prompt += f"\nOCR hint text:\n{hint_text[:500]}\n"
    if name_hint:
        prompt += f"\n{name_hint}\n"

    body = {
        "model": cfg.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }

    url = f"{cfg.base_url}/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.api_key}",
            "User-Agent": "PVH-Filename-Corrector/ai-color",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            detail = str(exc)
        return AIColorResult(note=f"AI HTTP {exc.code}: {detail}")
    except Exception as exc:
        return AIColorResult(note=f"AI error: {exc}")

    try:
        content = payload["choices"][0]["message"]["content"]
    except Exception:
        return AIColorResult(note="AI response missing content")

    parsed = _parse_ai_payload(_extract_json_object(content))
    if not parsed.color_code and not parsed.color_name:
        return AIColorResult(note=parsed.note or "AI did not find color code/name")
    return parsed


def should_ask_ai(
    cfg: AIColorConfig,
    *,
    has_ocr: bool,
    has_color_name: bool,
    has_color_code: bool,
) -> bool:
    if not cfg.usable:
        return False
    if cfg.mode == "always":
        return True
    # fallback: only when OCR missed the card, or found code/name incompletely.
    if not has_ocr:
        return True
    if has_color_code and has_color_name:
        return False
    return True
