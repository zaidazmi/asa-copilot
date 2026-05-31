"""Generate COMMANDS.md from Typer help output."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from asa_cli.main import app


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "COMMANDS.md"

COMMANDS = [
    [],
    ["config"],
    ["config", "discover-app"],
    ["campaigns"],
    ["adgroups"],
    ["keywords"],
    ["search-terms"],
    ["reports"],
    ["reports", "raw"],
    ["reports", "bid-recommendations"],
    ["budget"],
    ["geo"],
    ["ads"],
    ["acl"],
    ["optimize"],
    ["plan"],
    ["decisions"],
    ["apply"],
]


def _strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", value)


def _help_for(command: list[str]) -> str:
    result = CliRunner().invoke(app, [*command, "--help"], color=False)
    if result.exit_code != 0:
        raise RuntimeError(f"Help generation failed for {' '.join(command) or 'asa'}")
    return _strip_ansi(result.output).strip()


def main() -> None:
    sections = [
        "# Command Reference",
        "",
        "Generated from the current CLI help output.",
        "",
        "Regenerate with:",
        "",
        "```bash",
        "python scripts/generate_command_reference.py",
        "```",
        "",
    ]

    for command in COMMANDS:
        title = "asa" if not command else "asa " + " ".join(command)
        sections.extend([f"## `{title}`", "", "```text", _help_for(command), "```", ""])

    OUTPUT.write_text("\n".join(sections), encoding="utf-8")


if __name__ == "__main__":
    main()
