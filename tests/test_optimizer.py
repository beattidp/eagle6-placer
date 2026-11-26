"""Unit and integration tests for the Simulated Annealing local polish optimizer."""

from pathlib import Path

import pytest

from eagle6_placer.optimizer import (
    LocalPolishOptimizer,
    PolishConfig,
    RoutedCopperError,
)
from eagle6_placer.parser import EagleBoardParser


def test_polish_improves_tangled_board_and_preserves_invariants(
    tangled_polish_brd: Path,
) -> None:
    """SA polish must significantly reduce cost/wirelength/crossings with 0 violations."""
    board = EagleBoardParser().parse(tangled_polish_brd)
    cfg = PolishConfig(steps=3000, grid_mm=0.5, seed=42)
    result = LocalPolishOptimizer(board, cfg).optimize()

    assert result.final_violations == []
    assert result.best_cost.total_cost < result.initial_cost.total_cost
    assert (
        result.best_cost.weighted_mst_wirelength_mm
        < result.initial_cost.weighted_mst_wirelength_mm
    )
    assert result.best_cost.airwire_crossings <= result.initial_cost.airwire_crossings

    # Locked components must never move.
    for comp in board.locked_components:
        assert result.best_state.poses[comp.name] == comp.initial_pose

    # Keep-side invariant: no component may flip sides.
    for comp in board.components.values():
        assert (
            result.best_state.poses[comp.name].mirrored == comp.initial_pose.mirrored
        )


def test_polish_mixed_tht_keepout_preserves_sides_and_improves(
    mixed_tht_keepout_brd: Path,
) -> None:
    """Mixed THT/SMD + keepout + bottom-side board optimizes cleanly with 0 violations."""
    board = EagleBoardParser().parse(mixed_tht_keepout_brd)
    cfg = PolishConfig(steps=3000, grid_mm=0.5, seed=7)
    result = LocalPolishOptimizer(board, cfg).optimize()

    assert result.final_violations == []
    assert result.best_cost.total_cost < result.initial_cost.total_cost

    # Bottom SMDs R1 and R2 must remain mirrored.
    assert result.best_state.poses["R1"].mirrored is True
    assert result.best_state.poses["R2"].mirrored is True
    # Top SMDs C1 and C2 and THT L1 must remain unmirrored.
    assert result.best_state.poses["C1"].mirrored is False
    assert result.best_state.poses["C2"].mirrored is False
    assert result.best_state.poses["L1"].mirrored is False


def test_deterministic_seed_reproducibility(tangled_polish_brd: Path) -> None:
    """Identical seed and config must produce bit-identical results."""
    board = EagleBoardParser().parse(tangled_polish_brd)
    cfg = PolishConfig(steps=500, grid_mm=0.5, seed=12345)
    r1 = LocalPolishOptimizer(board, cfg).optimize()
    r2 = LocalPolishOptimizer(board, cfg).optimize()

    assert r1.best_state.poses == r2.best_state.poses
    assert r1.best_cost == r2.best_cost


def test_routed_copper_guard(tmp_path: Path, tangled_polish_brd: Path) -> None:
    """Unlocked parts on routed nets must raise RoutedCopperError unless opted in."""
    raw_xml = tangled_polish_brd.read_text(encoding="utf-8")
    routed_xml = raw_xml.replace(
        '<signal name="IN_A">',
        '<signal name="IN_A">\n<wire x1="5" y1="23.81" x2="15" y2="10" width="0.254" layer="1"/>',
    )
    routed_brd = tmp_path / "routed.brd"
    routed_brd.write_text(routed_xml, encoding="utf-8")

    board = EagleBoardParser().parse(routed_brd)
    assert "R1" in board.routed_unlocked_components()

    with pytest.raises(RoutedCopperError):
        LocalPolishOptimizer(board, PolishConfig(steps=50, allow_routed=False)).optimize()

    # Explicitly opting in succeeds.
    result = LocalPolishOptimizer(
        board, PolishConfig(steps=50, allow_routed=True)
    ).optimize()
    assert result.final_violations == []
