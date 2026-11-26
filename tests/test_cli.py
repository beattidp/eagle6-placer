"""End-to-end CLI tests for ``eagle6-placer polish``."""

import json
from pathlib import Path

from eagle6_placer.cli import main


def test_cli_polish_success(tmp_path: Path, tangled_polish_brd: Path) -> None:
    """CLI exits 0 and writes both .scr and .json outputs."""
    exit_code = main(
        [
            "polish",
            str(tangled_polish_brd),
            "--output-dir",
            str(tmp_path),
            "--steps",
            "1000",
            "--seed",
            "42",
        ]
    )
    assert exit_code == 0
    scr = tmp_path / "tangled_polish_placed.scr"
    rep = tmp_path / "tangled_polish_placed.json"
    assert scr.is_file()
    assert rep.is_file()
    data = json.loads(rep.read_text(encoding="utf-8"))
    assert data["constraint_audit"]["passed"] is True


def test_cli_missing_file_returns_nonzero(tmp_path: Path) -> None:
    """CLI returns non-zero exit code on missing input board."""
    exit_code = main(["polish", str(tmp_path / "nonexistent.brd")])
    assert exit_code == 2
