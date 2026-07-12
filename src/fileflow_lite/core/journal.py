from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) / "FileFlowLite" if base else Path.home() / ".fileflow_lite"
    root.mkdir(parents=True, exist_ok=True)
    return root


def log_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def write_journal(payload: dict[str, Any]) -> Path:
    payload.setdefault("journal_version", 1)
    payload.setdefault("finished_at", datetime.now(timezone.utc).isoformat())
    operation_id = payload.get("id", "unknown")
    destination = log_dir() / f"{operation_id}.json"
    _atomic_json(destination, payload)
    _atomic_json(app_data_dir() / "latest.json", payload)
    return destination


def load_latest() -> dict[str, Any] | None:
    path = app_data_dir() / "latest.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        if data.get("status") != "success" or data.get("undone_at"):
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None


def mark_undone(payload: dict[str, Any]) -> None:
    payload["undone_at"] = datetime.now(timezone.utc).isoformat()
    write_journal(payload)

