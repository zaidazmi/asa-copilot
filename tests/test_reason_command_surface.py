"""Regression tests for reason capture on live mutation commands."""

from typer.testing import CliRunner

from asa_cli.main import app


def test_live_mutation_commands_expose_reason_option():
    runner = CliRunner()
    commands = [
        ["ads", "create"],
        ["ads", "delete"],
        ["geo", "set"],
        ["keywords", "add"],
        ["keywords", "add-negatives"],
        ["keywords", "promote"],
        ["keywords", "delete"],
        ["keywords", "update-bid"],
        ["keywords", "pause"],
        ["keywords", "enable"],
        ["keywords", "delete-negatives"],
        ["keywords", "update-bids-bulk"],
    ]

    for command in commands:
        result = runner.invoke(app, [*command, "--help"])

        assert result.exit_code == 0, " ".join(command)
        assert "--reason" in result.output, " ".join(command)
