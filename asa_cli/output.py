"""Shared JSON output helpers for CLI automation surfaces."""

from __future__ import annotations

import json
from typing import Any

_json_format = "pretty"


def set_json_format(value: str | None) -> None:
    """Set process-local JSON output format for the current CLI invocation."""
    global _json_format
    if value in {None, "json", "pretty"}:
        _json_format = "pretty"
        return
    if value == "compact":
        _json_format = "compact"
        return
    raise ValueError("Format must be 'json', 'pretty', or 'compact'.")


def json_dumps(data: Any) -> str:
    """Serialize JSON according to the selected CLI format."""
    if _json_format == "compact":
        return json.dumps(data, separators=(",", ":"))
    return json.dumps(data, indent=2)


def print_json(data: Any) -> None:
    """Print JSON according to the selected CLI format."""
    print(json_dumps(data))


def print_json_error(message: str) -> None:
    """Print a machine-readable error payload."""
    print_json({"error": message})
