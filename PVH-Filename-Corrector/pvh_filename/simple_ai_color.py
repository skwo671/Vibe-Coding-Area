"""Optional AI vision helper for photo renaming (color + angle).

Default provider: local Ollama (free, no cloud, no region lock).
  Install: https://ollama.com/ then `ollama pull llava`

Also supports: Qwen-VL, OpenRouter, Gemini.

Enabled via AI設定.txt or env:
  PVH_AI_ENABLED=1
  PVH_AI_BASE_URL=http://127.0.0.1:11434/v1
  PVH_AI_MODEL=llava
  PVH_AI_MODE=always|fallback
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
from pvh_filename.simple_labels import ANGLE_ALIAS, ANGLE_LABELS, normalize_token
from pvh_filename.simple_ocr import ARCHROMA_CODE_RE, CWF_LABEL_RE

CONFIG_NAMES = ("AI設定.txt", "ai_config.txt", "AI_CONFIG.txt")

# Default: local Ollama vision (free / offline-friendly).
DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "llava"


@dataclass(frozen=True)
class AIColorConfig:
    enabled: bool = False
    mode: str = "fallback"  # fallback | always | off
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    json_mode: bool = False
    source: str = ""

    def is_local(self) -> bool:
        host = (self.base_url or "").lower()
        return any(
            token in host
            for token in (
                "127.0.0.1",
                "localhost",
                "0.0.0.0",
                "::1",
            )
        )

    def is_gemini(self) -> bool:
        host = (self.base_url or "").lower()
        model = (self.model or "").lower()
        return "generativelanguage.googleapis.com" in host or model.startswith("gemini")

    def is_qwen(self) -> bool:
        host = (self.base_url or "").lower()
        model = (self.model or "").lower()
        return (
            "dashscope" in host
            or "maas.aliyuncs.com" in host
            or model.startswith("qwen")
        )

    def is_openrouter(self) -> bool:
        return "openrouter.ai" in (self.base_url or "").lower()

    def is_deepseek(self) -> bool:
        host = (self.base_url or "").lower()
        model = (self.model or "").lower()
        return "api.deepseek.com" in host or (
            model.startswith("deepseek") and "openrouter" not in host
        )

    def supports_vision(self) -> bool:
        """DeepSeek official API is text-only (no image_url)."""
        if self.is_deepseek() and not self.is_openrouter():
            return False
        return True

    @property
    def usable(self) -> bool:
        if not self.enabled or self.mode == "off":
            return False
        # Local Ollama / LM Studio usually accept any/empty key.
        if self.is_local():
            return True
        return bool(self.api_key)


@dataclass(frozen=True)
class AIColorResult:
    color_code: str = ""
    color_name: str = ""
    has_cwf_label: bool = False
    light_source: str = "D65"
    note: str = ""


@dataclass(frozen=True)
class AIPhotoResult:
    """Unified AI classification for rename: color card or product angle."""

    kind: str = ""  # color | angle
    angle: str = ""  # AS | FRONT | SIDE | CORNER
    color_code: str = ""
    color_name: str = ""
    has_cwf_label: bool = False
    light_source: str = "D65"
    note: str = ""

    @property
    def usable_color(self) -> bool:
        return self.kind == "color" and bool(self.color_code or self.color_name)

    @property
    def usable_angle(self) -> bool:
        return self.kind == "angle" and self.angle in ANGLE_LABELS


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
        or os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or file_data.get("api_key")
        or file_data.get("dashscope_api_key")
        or file_data.get("gemini_api_key")
        or file_data.get("deepseek_api_key")
        or file_data.get("openai_api_key")
        or ""
    ).strip()
    base_url = (
        os.environ.get("PVH_AI_BASE_URL")
        or file_data.get("base_url")
        or DEFAULT_BASE_URL
    ).strip().rstrip("/")
    model = (
        os.environ.get("PVH_AI_MODEL") or file_data.get("model") or DEFAULT_MODEL
    ).strip()

    # Force JSON mode off for most vision providers by default.
    default_json = "0"
    if "api.openai.com" in base_url.lower():
        default_json = "1"
    json_mode_raw = os.environ.get("PVH_AI_JSON_MODE")
    if json_mode_raw is None:
        json_mode_raw = file_data.get("json_mode", default_json)
    json_mode = _parse_bool(str(json_mode_raw))

    cfg = AIColorConfig(
        enabled=False,
        mode=mode,
        api_key=api_key,
        base_url=base_url,
        model=model,
        json_mode=json_mode,
        source=source,
    )
    enabled = _parse_bool(str(enabled_raw)) and mode != "off" and (
        bool(api_key) or cfg.is_local()
    )
    return AIColorConfig(
        enabled=enabled,
        mode=mode if enabled else "off",
        api_key=api_key or ("ollama" if cfg.is_local() else ""),
        base_url=base_url,
        model=model,
        json_mode=json_mode,
        source=source,
    )


def ollama_is_reachable(base_url: str = DEFAULT_BASE_URL, timeout_sec: float = 2.0) -> bool:
    """Probe local Ollama HTTP API."""
    root = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    for path in ("/api/tags", "/"):
        try:
            req = urllib.request.Request(
                f"{root}{path}",
                headers={"User-Agent": "PVH-Filename-Corrector/ollama-check"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                if 200 <= getattr(resp, "status", 200) < 300:
                    return True
        except Exception:
            continue
    return False


def ollama_has_model(model: str, base_url: str = DEFAULT_BASE_URL, timeout_sec: float = 3.0) -> bool | None:
    """Return True/False if tags listing works; None if Ollama unreachable."""
    root = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    try:
        req = urllib.request.Request(
            f"{root}/api/tags",
            headers={"User-Agent": "PVH-Filename-Corrector/ollama-check"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    needle = (model or "").split(":")[0].lower()
    for item in payload.get("models") or []:
        name = str(item.get("name") or item.get("model") or "").lower()
        if name == (model or "").lower() or name.startswith(needle + ":") or name == needle:
            return True
    return False


def ai_status_message(cfg: AIColorConfig | None = None) -> str:
    cfg = cfg or load_ai_config()
    if not cfg.usable:
        return "AI 改名: 未啟用（本機 Ollama：裝 https://ollama.com/ 後 ollama pull llava）"
    where = f" / {Path(cfg.source).name}" if cfg.source else ""
    if cfg.is_deepseek() and not cfg.supports_vision():
        return (
            "AI 改名: DeepSeek 已設定但官方 API 唔支援睇相"
            "（請改用本機 Ollama llava）"
            f"{where}"
        )
    if cfg.is_local():
        if not ollama_is_reachable(cfg.base_url):
            return (
                "AI 改名: Ollama 未啟動（請開 Ollama 或執行 ollama serve）"
                f"{where}"
            )
        has = ollama_has_model(cfg.model, cfg.base_url)
        if has is False:
            return (
                f"AI 改名: Ollama 已開但未下載模型 {cfg.model}"
                f"（請執行 ollama pull {cfg.model}）{where}"
            )
        return f"AI 改名: 已啟用 Ollama ({cfg.mode}, {cfg.model}{where})"
    if cfg.is_qwen():
        provider = "Qwen-VL"
    elif cfg.is_gemini():
        provider = "Gemini"
    elif cfg.is_openrouter():
        provider = "OpenRouter"
    elif cfg.is_deepseek():
        provider = "DeepSeek"
    else:
        provider = "AI"
    return f"AI 改名: 已啟用 {provider} ({cfg.mode}, {cfg.model}{where})"


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
    # Gemini sometimes wraps JSON in ```json fences.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S | re.I)
    if fenced:
        text = fenced.group(1)
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


def _chat_vision_json(
    path: Path,
    cfg: AIColorConfig,
    prompt: str,
    *,
    timeout_sec: float = 60.0,
) -> tuple[dict, str]:
    """
    Send image + prompt to OpenAI-compatible vision chat.
    Returns (parsed_json, error_note). error_note set on failure.
    """
    data_url = _image_to_data_url(path)
    if not data_url:
        return {}, "failed to load image"

    body = {
        "model": cfg.model,
        "temperature": 0,
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
    if cfg.json_mode:
        body["response_format"] = {"type": "json_object"}

    url = f"{cfg.base_url.rstrip('/')}/chat/completions"

    def _post(request_body: dict) -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.api_key or 'ollama'}",
                "User-Agent": "PVH-Filename-Corrector/ai-vision",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        payload = _post(body)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            detail = str(exc)
        if cfg.json_mode and "response_format" in body and exc.code in {400, 404, 422}:
            retry_body = dict(body)
            retry_body.pop("response_format", None)
            try:
                payload = _post(retry_body)
            except Exception as retry_exc:
                return {}, f"AI HTTP {exc.code}: {detail}; retry: {retry_exc}"
        else:
            return {}, f"AI HTTP {exc.code}: {detail}"
    except Exception as exc:
        return {}, f"AI error: {exc}"

    try:
        content = payload["choices"][0]["message"]["content"]
    except Exception:
        return {}, "AI response missing content"
    if isinstance(content, list):
        content = " ".join(
            str(part.get("text", part)) if isinstance(part, dict) else str(part)
            for part in content
        )
    return _extract_json_object(str(content)), ""


def _normalize_angle_label(value: object) -> str:
    text = normalize_token(str(value or ""))
    if not text:
        return ""
    if text in ANGLE_LABELS:
        return text
    return ANGLE_ALIAS.get(text, "")


def _parse_photo_payload(data: dict) -> AIPhotoResult:
    kind = normalize_token(str(data.get("kind") or data.get("type") or "")).lower()
    if kind in {"color", "colour", "swatch", "color_card", "colorcard"}:
        kind = "color"
    elif kind in {"angle", "product", "garment", "label"}:
        kind = "angle"
    else:
        # Infer from fields.
        if data.get("color_code") or data.get("color_name") or data.get("code"):
            kind = "color"
        elif data.get("angle") or data.get("view"):
            kind = "angle"
        else:
            kind = ""

    color = _parse_ai_payload(data)
    angle = _normalize_angle_label(data.get("angle") or data.get("view") or data.get("suffix"))
    note = str(data.get("note") or data.get("reason") or color.note or "").strip()
    return AIPhotoResult(
        kind=kind,
        angle=angle,
        color_code=color.color_code,
        color_name=color.color_name,
        has_cwf_label=color.has_cwf_label,
        light_source=color.light_source,
        note=note,
    )


def classify_photo_with_ai(
    path: Path,
    cfg: AIColorConfig,
    *,
    master_names: list[str] | None = None,
    hint_text: str = "",
    timeout_sec: float | None = None,
) -> AIPhotoResult | None:
    """Classify a photo as color-card or angle, and extract rename fields."""
    if not cfg.usable:
        return None
    if not cfg.supports_vision():
        return AIPhotoResult(
            note=(
                "目前供應商唔支援睇相（例如 DeepSeek 官方 API）。"
                "請改用本機 Ollama：base_url=http://127.0.0.1:11434/v1 model=llava"
            )
        )
    if timeout_sec is None:
        timeout_sec = 180.0 if cfg.is_local() else 60.0
    if cfg.is_local() and not ollama_is_reachable(cfg.base_url):
        return AIPhotoResult(note="Ollama 未啟動，請先開 Ollama（ollama serve）")
    names = [n for n in (master_names or []) if n][:50]
    name_hint = ""
    if names:
        name_hint = "Known Archroma color names (prefer exact match):\n" + ", ".join(names)

    prompt = (
        "You rename Tommy Hilfiger product photos for a factory workflow.\n"
        "Decide if this image is a COLOR swatch card or an ANGLE product shot.\n"
        "Return ONLY one JSON object with keys:\n"
        '  kind: "color" or "angle"\n'
        '  angle: one of "AS","FRONT","SIDE","CORNER" (only when kind=angle; else "")\n'
        '  color_code: like "654-920" (only when kind=color; else "")\n'
        '  color_name: like "DESERT SKY" (only when kind=color; else "")\n'
        "  has_cwf_label: boolean true ONLY if a CWF sticker/label is visible\n"
        "  note: short reason\n"
        "Rules for COLOR:\n"
        "- Archroma white header card with fabric swatch, printed name + ###-### code.\n"
        "- has_cwf_label true only with a clear CWF label/sticker.\n"
        "Rules for ANGLE:\n"
        "- AS: two almost identical product patterns side-by-side (actual size duplicates).\n"
        "- FRONT: single product / woven label shown mostly from the front.\n"
        "- SIDE: product / label shown from the side profile.\n"
        "- CORNER: product / label corner/edge-focused view.\n"
        "- If unsure between FRONT/SIDE/CORNER, prefer FRONT.\n"
        "- Do not wrap JSON in markdown fences.\n"
    )
    if hint_text:
        prompt += f"\nHint:\n{hint_text[:400]}\n"
    if name_hint:
        prompt += f"\n{name_hint}\n"

    data, err = _chat_vision_json(path, cfg, prompt, timeout_sec=timeout_sec)
    if err and not data:
        return AIPhotoResult(note=err)
    parsed = _parse_photo_payload(data)
    if not parsed.kind:
        return AIPhotoResult(note=parsed.note or err or "AI did not classify photo")
    if parsed.kind == "color" and not (parsed.color_code or parsed.color_name):
        return AIPhotoResult(
            kind="color",
            note=parsed.note or "AI said color but found no code/name",
        )
    if parsed.kind == "angle" and parsed.angle not in ANGLE_LABELS:
        return AIPhotoResult(
            kind="angle",
            note=parsed.note or "AI said angle but gave no valid AS/FRONT/SIDE/CORNER",
        )
    if err and not parsed.note:
        return AIPhotoResult(
            kind=parsed.kind,
            angle=parsed.angle,
            color_code=parsed.color_code,
            color_name=parsed.color_name,
            has_cwf_label=parsed.has_cwf_label,
            light_source=parsed.light_source,
            note=err,
        )
    return parsed


def read_color_card_with_ai(
    path: Path,
    cfg: AIColorConfig,
    *,
    hint_text: str = "",
    master_names: list[str] | None = None,
    timeout_sec: float | None = None,
) -> AIColorResult | None:
    """Ask a vision LLM to read Archroma color name / code / CWF."""
    if not cfg.usable:
        return None
    if not cfg.supports_vision():
        return AIColorResult(
            note=(
                "目前供應商唔支援睇相（例如 DeepSeek 官方 API）。"
                "請改用本機 Ollama llava。"
            )
        )
    if timeout_sec is None:
        timeout_sec = 180.0 if cfg.is_local() else 60.0
    if cfg.is_local() and not ollama_is_reachable(cfg.base_url):
        return AIColorResult(note="Ollama 未啟動，請先開 Ollama（ollama serve）")
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
        "- Do not wrap the JSON in markdown fences.\n"
    )
    if hint_text:
        prompt += f"\nOCR hint text:\n{hint_text[:500]}\n"
    if name_hint:
        prompt += f"\n{name_hint}\n"

    data, err = _chat_vision_json(path, cfg, prompt, timeout_sec=timeout_sec)
    if err and not data:
        return AIColorResult(note=err)
    parsed = _parse_ai_payload(data)
    if not parsed.color_code and not parsed.color_name:
        return AIColorResult(note=parsed.note or err or "AI did not find color code/name")
    if err and not parsed.note:
        return AIColorResult(
            color_code=parsed.color_code,
            color_name=parsed.color_name,
            has_cwf_label=parsed.has_cwf_label,
            light_source=parsed.light_source,
            note=err,
        )
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


def should_ask_ai_angle(
    cfg: AIColorConfig,
    *,
    local_suffix: str,
    local_source: str,
) -> bool:
    """Whether to ask AI for angle classification."""
    if not cfg.usable:
        return False
    if cfg.mode == "always":
        return True
    # fallback: only when local path was weak/default.
    if local_source in {"single_product", "model"}:
        return True
    if local_suffix == "FRONT" and local_source.startswith("heuristic"):
        return True
    return False
