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


def test_cli_allow_mirror_and_restrict_mirror(
    tmp_path: Path, mixed_tht_keepout_brd: Path
) -> None:
    """CLI --allow-mirror with range spec and --restrict-mirror executes cleanly."""
    exit_code = main(
        [
            "polish",
            str(mixed_tht_keepout_brd),
            "--output-dir",
            str(tmp_path),
            "--steps",
            "500",
            "--seed",
            "7",
            "--allow-mirror",
            "{C1..C2},{R1..R2}",
            "--restrict-mirror",
            "R2",
        ]
    )
    assert exit_code == 0
    rep = json.loads((tmp_path / "mixed_tht_keepout_placed.json").read_text(encoding="utf-8"))
    assert rep["constraint_audit"]["passed"] is True
    # Restricted R2 must remain on bottom (MR*).
    for d in rep["deltas"]:
        if d["name"] == "R2":
            assert d["new_rot"].startswith("MR")
