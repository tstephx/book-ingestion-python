"""analyze-merges is analysis-only (book-ingestion-python#12)."""

import click
from click.testing import CliRunner

from book_ingestion.cli_enhanced import register_enhanced_commands


def _cli():
    @click.group()
    def cli():
        pass

    register_enhanced_commands(cli)
    return cli


def test_analyze_merges_registered_and_legacy_alias_hidden():
    cli = _cli()
    assert "analyze-merges" in cli.commands
    legacy = cli.commands["merge-chapters"]
    assert legacy.hidden and legacy.deprecated


def test_help_does_not_promise_a_merge():
    result = CliRunner().invoke(_cli(), ["analyze-merges", "--help"])
    assert result.exit_code == 0
    assert "never modifies" in result.output
    assert "--dry-run" not in result.output  # hidden no-op


def test_unknown_book_exits_cleanly(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_PIPELINE_DB", str(tmp_path / "x.db"))
    result = CliRunner().invoke(_cli(), ["analyze-merges", "nope"])
    assert "not implemented" not in result.output
