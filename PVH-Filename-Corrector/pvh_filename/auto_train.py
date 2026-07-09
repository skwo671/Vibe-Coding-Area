from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pvh_filename.model import train_suffix_model


def state_path(model_dir: Path) -> Path:
    return model_dir / "run_state.json"


def load_state(model_dir: Path) -> dict:
    path = state_path(model_dir)
    if not path.exists():
        return {"runs_since_train": 0, "total_runs": 0, "last_trained_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(model_dir: Path, state: dict) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    state_path(model_dir).write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def record_run_and_maybe_train(
    *,
    model_dir: Path,
    training_data: Path,
    every: int = 5,
    enabled: bool = True,
) -> dict:
    state = load_state(model_dir)
    state["runs_since_train"] = int(state.get("runs_since_train", 0)) + 1
    state["total_runs"] = int(state.get("total_runs", 0)) + 1
    state["auto_train_triggered"] = False

    if enabled and every > 0 and state["runs_since_train"] >= every:
        metrics = train_suffix_model(training_data, model_dir)
        state["runs_since_train"] = 0
        state["last_trained_at"] = datetime.now().isoformat(timespec="seconds")
        state["last_train_metrics"] = metrics
        state["auto_train_triggered"] = True

    save_state(model_dir, state)
    return state
