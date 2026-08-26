"""Tests for scripts/check_portability.sh's ALLOWLIST matching (book-ingestion-python#9).

The ALLOWLIST used to match an allowed line by bare substring
containment anywhere in the line, not anchored to the line's actual
shape -- so an unrelated line elsewhere in the same file containing the
same substring would also be incorrectly allowlisted. These tests pin
down the fix: allowlist entries are "file:regex" pairs matched via an
anchored regex against the full (whitespace-stripped) line.
"""

import subprocess
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_portability.sh"


def _init_repo(repo_dir):
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)


def _write_and_track(repo_dir, relative_path, content):
    target = repo_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    subprocess.run(["git", "add", relative_path], cwd=repo_dir, check=True)


def _script_with_allowlist(repo_dir, entries):
    """Copy check_portability.sh into repo_dir with ALLOWLIST replaced by `entries`."""
    original = SCRIPT.read_text()
    start = original.index("ALLOWLIST=(")
    end = original.index(")\n", start) + 2
    entries_src = "".join(f"  '{e}'\n" for e in entries)
    patched = original[:start] + "ALLOWLIST=(\n" + entries_src + ")\n" + original[end:]
    patched_path = repo_dir / "check_portability.sh"
    patched_path.write_text(patched)
    patched_path.chmod(0o755)
    return patched_path


def _run(script_path, repo_dir):
    return subprocess.run(["bash", str(script_path)], cwd=repo_dir, capture_output=True, text=True)


def test_passes_when_no_hardcoded_paths(tmp_path):
    _init_repo(tmp_path)
    _write_and_track(tmp_path, ".claude/settings.json", '{"key": "value"}\n')

    result = _run(SCRIPT, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Portability check passed" in result.stdout


def test_fails_on_unallowlisted_hardcoded_path(tmp_path):
    _init_repo(tmp_path)
    _write_and_track(tmp_path, ".claude/settings.json", '{"path": "/Users/tester/pin"}\n')

    result = _run(SCRIPT, tmp_path)

    assert result.returncode == 1
    assert "/Users/tester/pin" in result.stderr


def test_allowlist_entry_permits_its_exact_line_shape(tmp_path):
    _init_repo(tmp_path)
    _write_and_track(
        tmp_path,
        ".claude/settings.json",
        textwrap.dedent(
            """\
            {
              "path": "/Users/tester/pin"
            }
            """
        ),
    )
    script = _script_with_allowlist(
        tmp_path, ['.claude/settings.json:^"path": "/Users/tester/pin"$']
    )

    result = _run(script, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Portability check passed" in result.stdout


def test_allowlist_entry_does_not_match_unrelated_line_with_same_substring(tmp_path):
    """book-ingestion-python#9: a substring match must not allowlist an
    unrelated line elsewhere in the file just because it happens to
    contain the same text -- only the exact anchored line shape is
    permitted.
    """
    _init_repo(tmp_path)
    _write_and_track(
        tmp_path,
        ".claude/settings.json",
        textwrap.dedent(
            """\
            {
              "other_field": "/Users/tester/pin-debug-copy/notes.txt"
              "path": "/Users/tester/pin"
            }
            """
        ),
    )
    script = _script_with_allowlist(
        tmp_path, ['.claude/settings.json:^"path": "/Users/tester/pin"$']
    )

    result = _run(script, tmp_path)

    assert result.returncode == 1
    assert "other_field" in result.stderr
    assert '"path": "/Users/tester/pin"' not in result.stderr
