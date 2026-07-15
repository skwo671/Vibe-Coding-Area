#!/usr/bin/env python3
"""Simple PVH rename tool: work mode + learn mode."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
from pathlib import Path

from pvh_filename.runtime import default_model_dir, default_target_folder, is_frozen, portable_root
from pvh_filename.simple_ai_color import AIColorConfig, load_ai_config
from pvh_filename.simple_learn import learn_from_folder
from pvh_filename.simple_work import predict_work_folder


def configure_frozen_runtime() -> None:
    """Avoid PyInstaller + joblib/loky worker re-entry crashes on Windows."""
    if not is_frozen():
        return
    os.environ.setdefault("JOBLIB_MULTIPROCESSING", "0")
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    hf_home = portable_root() / "models" / "huggingface"
    if hf_home.exists():
        os.environ["HF_HOME"] = str(hf_home)
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"


def pause_if_windows() -> None:
    if is_frozen() and sys.platform == "win32":
        input("\n按 Enter 關閉...")


def resolve_target(folder: Path | None) -> Path:
    if folder is not None:
        return folder
    cwd = Path.cwd()
    candidate = cwd / "待改名圖片"
    if candidate.is_dir():
        return candidate
    if is_frozen():
        root = portable_root()
        packaged = root / "待改名圖片"
        if packaged.is_dir():
            return packaged
        return cwd
    return default_target_folder()


def resolve_ai_config(folder: Path, args: argparse.Namespace) -> AIColorConfig:
    cfg = load_ai_config(folder)
    if args.no_ai:
        return AIColorConfig(enabled=False, mode="off", json_mode=cfg.json_mode, source=cfg.source)
    if args.ai:
        api_key = cfg.api_key or os.environ.get("OPENAI_API_KEY", "")
        mode = args.ai_mode or (cfg.mode if cfg.mode != "off" else "fallback")
        probe = AIColorConfig(
            enabled=True,
            mode=mode,
            api_key=api_key,
            base_url=cfg.base_url,
            model=args.ai_model or cfg.model,
            json_mode=cfg.json_mode,
            source=cfg.source or "cli --ai",
        )
        ok = bool(api_key) or probe.is_local()
        return AIColorConfig(
            enabled=ok,
            mode=mode if ok else "off",
            api_key=api_key or ("ollama" if probe.is_local() else ""),
            base_url=cfg.base_url,
            model=args.ai_model or cfg.model,
            json_mode=cfg.json_mode,
            source=cfg.source or "cli --ai",
        )
    if args.ai_mode:
        return AIColorConfig(
            enabled=cfg.enabled and args.ai_mode != "off",
            mode=args.ai_mode,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model=args.ai_model or cfg.model,
            json_mode=cfg.json_mode,
            source=cfg.source,
        )
    if args.ai_model and cfg.usable:
        return AIColorConfig(
            enabled=cfg.enabled,
            mode=cfg.mode,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model=args.ai_model,
            json_mode=cfg.json_mode,
            source=cfg.source,
        )
    return cfg


def main() -> int:
    configure_frozen_runtime()
    parser = argparse.ArgumentParser(description="PVH 簡化改名工具：工作模式 / 學習模式")
    parser.add_argument("mode", choices=["work", "learn"], help="work=自動改名, learn=從正確檔名學習")
    parser.add_argument("folder", nargs="?", type=Path, default=None)
    parser.add_argument("--model", type=Path, default=default_model_dir())
    parser.add_argument("--dry-run", action="store_true", help="工作模式只報告唔改名")
    parser.add_argument("--ai", action="store_true", help="啟用 AI 協助讀色名（需要 API key）")
    parser.add_argument("--no-ai", action="store_true", help="強制關閉 AI")
    parser.add_argument(
        "--ai-mode",
        choices=["fallback", "always", "off"],
        default=None,
        help="AI 模式：fallback=OCR失敗才問；always=對色相都問",
    )
    parser.add_argument("--ai-model", default=None, help="AI 模型名，例如 gpt-4o-mini")
    args = parser.parse_args()

    folder = resolve_target(args.folder)
    if not folder.is_dir():
        print(f"找不到資料夾: {folder}")
        pause_if_windows()
        return 1

    print(f"模式: {args.mode}")
    print(f"資料夾: {folder}")
    print(f"模型目錄: {args.model}")
    print()

    try:
        if args.mode == "work":
            summary = predict_work_folder(
                folder,
                args.model,
                apply=not args.dry_run,
                write_report=True,
                ai_config=resolve_ai_config(folder, args),
            )
        else:
            summary = learn_from_folder(folder, args.model)
    except Exception as exc:
        print(f"執行失敗: {exc}")
        pause_if_windows()
        return 1

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    pause_if_windows()
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
