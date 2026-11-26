"""Tests for M2.3 coarse-to-fine placement and M2.4 multi-seed candidates."""

import json
from pathlib import Path

from eagle6_placer.cli import main
from eagle6_placer.coarse import CoarseConfig, CoarsePlacer
from eagle6_placer.constraints import ConstraintChecker
from eagle6_placer.parser import EagleBoardParser


def test_coarse_placer_brings_offboard_parts_inside_legally(
    unplaced_fresh_brd: Path,
) -> None:
    """Force-directed + spiral legalizer must place all off-board parts inside with 0 violations."""
    board = EagleBoardParser().parse(unplaced_fresh_brd)
    checker = ConstraintChecker(board)
    assert len(checker.audit_state(board.initial_state())) > 0

    coarse_state = CoarsePlacer(board, CoarseConfig(grid_mm=0.5, seed=42)).place_coarse()
    assert checker.audit_state(coarse_state) == []

    # Locked connectors J1 and J2 must stay untouched.
    for locked in board.locked_components:
        assert coarse_state.poses[locked.name] == locked.initial_pose


def test_cli_place_and_candidates_manifest(
    tmp_path: Path, unplaced_fresh_brd: Path
) -> None:
    """CLI 'place' with --candidates 3 and --keep-all-candidates emits valid manifest & scripts."""
    exit_code = main(
        [
            "place",
            str(unplaced_fresh_brd),
            "--output-dir",
            str(tmp_path),
            "--steps",
            "800",
            "--seed",
            "10",
            "--candidates",
            "3",
            "--keep-all-candidates",
            "--preview",
        ]
    )
    assert exit_code == 0

    manifest_path = tmp_path / "candidates_manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "place"
    assert manifest["candidate_count"] == 3
    assert len(manifest["candidates"]) == 3

    # Candidates must be sorted best-first and all pass audit.
    costs = [c["total_cost"] for c in manifest["candidates"]]
    assert costs == sorted(costs)
    for rec in manifest["candidates"]:
        assert rec["passed_audit"] is True
        assert Path(rec["script_path"]).is_file()
        assert Path(rec["report_path"]).is_file()

    assert (tmp_path / "unplaced_fresh_placed.scr").is_file()
    assert (tmp_path / "unplaced_fresh_preview.svg").is_file()
