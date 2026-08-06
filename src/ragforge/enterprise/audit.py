"""Structured audit logging — who did what, when."""

import json
import time
from pathlib import Path
from datetime import datetime, timezone


def audit_log(action: str, tenant: str, detail: str = "", actor: str = "api") -> None:
    """Write a structured audit log entry.

    ponytail: append to JSONL file — simple, parseable, no DB needed.
    Rotate by date if the file grows past 10MB.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "tenant": tenant,
        "actor": actor,
        "detail": detail,
    }
    log_file = Path("./audit.jsonl")
    _rotate_if_large(log_file)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _rotate_if_large(filepath: Path, max_mb: int = 10) -> None:
    if filepath.exists() and filepath.stat().st_size > max_mb * 1024 * 1024:
        ts = time.strftime("%Y%m%d_%H%M%S")
        filepath.rename(filepath.with_suffix(f".{ts}.jsonl"))
