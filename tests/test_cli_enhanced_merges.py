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


def test_legacy_alias_still_invokes():
    result = CliRunner().invoke(_cli(), ["merge-chapters", "--help"])
    assert result.exit_code == 0
    assert "never modifies" in result.output


def _db(monkeypatch, tmp_path):
    from book_ingestion.storage.database import BookDatabase

    path = tmp_path / "x.db"
    monkeypatch.setenv("AGENTIC_PIPELINE_DB", str(path))
    db = BookDatabase(path)
    db.initialize()
    return db


def test_unknown_book_reports_not_found(monkeypatch, tmp_path):
    _db(monkeypatch, tmp_path)
    result = CliRunner().invoke(_cli(), ["analyze-merges", "nope"])
    assert result.exit_code == 0
    assert "Book not found: nope" in result.output
    assert "not implemented" not in result.output


def test_prints_plan_and_leaves_chapters_untouched(monkeypatch, tmp_path):
    db = _db(monkeypatch, tmp_path)
    db.insert_book({"id": "b1", "title": "Frag Book"})
    for n, words in enumerate([5000, 400, 6000], start=1):
        db.insert_chapter(
            {"id": f"c{n}", "book_id": "b1", "chapter_number": n,
             "title": f"Ch {n}", "word_count": words}
        )
    before = db.get_chapters_by_book("b1")

    result = CliRunner().invoke(_cli(), ["analyze-merges", "b1"])

    assert result.exit_code == 0, result.output
    assert "Merge" in result.output
    assert "Analysis only" in result.output
    assert db.get_chapters_by_book("b1") == before
