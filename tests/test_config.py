"""Tests for Config's database_path resolution (book-ingestion-python#2).

CLAUDE.md asserts code always points at the canonical DB, never a
repo-local data/library.db -- but Config (used by the primary CLI's 12
call sites) never read AGENTIC_PIPELINE_DB, only reingest_books.py did,
via its own separate os.environ.get() call. These tests pin down the
fix: Config.database_path must honor AGENTIC_PIPELINE_DB when set,
falling back to the configured/default local path only when unset.
"""

import json

from book_ingestion.utils.config import Config


def test_database_path_honors_env_override(tmp_path, monkeypatch):
    """AGENTIC_PIPELINE_DB must win over config.json's database_path."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "output_dir": str(tmp_path / "books"),
                "database_path": str(tmp_path / "local-dev-copy.db"),
                "temp_dir": str(tmp_path / "temp"),
            }
        )
    )
    canonical = tmp_path / "canonical-library.db"
    monkeypatch.setenv("AGENTIC_PIPELINE_DB", str(canonical))

    config = Config(config_path=str(config_file))

    assert config.database_path == canonical, (
        "AGENTIC_PIPELINE_DB was set but database_path still resolved to "
        "the config.json / default local path — every CLI entry point "
        "that doesn't pass an explicit override will silently write to "
        "the wrong database."
    )


def test_database_path_falls_back_to_config_when_env_unset(tmp_path, monkeypatch):
    """With no AGENTIC_PIPELINE_DB, database_path keeps today's behavior."""
    monkeypatch.delenv("AGENTIC_PIPELINE_DB", raising=False)
    config_file = tmp_path / "config.json"
    local_db = tmp_path / "local-dev-copy.db"
    config_file.write_text(
        json.dumps(
            {
                "output_dir": str(tmp_path / "books"),
                "database_path": str(local_db),
                "temp_dir": str(tmp_path / "temp"),
            }
        )
    )

    config = Config(config_path=str(config_file))

    assert config.database_path == local_db


def test_defaults_also_honor_env_override(tmp_path, monkeypatch):
    """No config.json at all (falls through to _get_defaults()) must also
    honor AGENTIC_PIPELINE_DB, not just the config.json-present path."""
    canonical = tmp_path / "canonical-library.db"
    monkeypatch.setenv("AGENTIC_PIPELINE_DB", str(canonical))

    config = Config(config_path=str(tmp_path / "does-not-exist.json"))

    assert config.database_path == canonical
