from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_root() -> Path:
    """Directory containing the app (project root, or exe folder when packaged)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def portable_root() -> Path:
    """Root of the portable package (parent of app/ when packaged)."""
    root = app_root()
    if is_frozen() and root.name == "app":
        return root.parent
    return root


def default_model_dir() -> Path:
    if is_frozen():
        packaged = portable_root() / "models" / "suffix_classifier"
        if packaged.exists():
            return packaged
    return app_root() / "models" / "suffix_classifier"


def default_target_folder() -> Path:
    """Folder to rename when no path is passed on the command line."""
    if is_frozen():
        return Path.cwd()
    return app_root()
