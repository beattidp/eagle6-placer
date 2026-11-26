"""Unit tests for hard placement constraints (overlap, THT, keepouts, holes)."""

from pathlib import Path

from eagle6_placer.constraints import ConstraintChecker
from eagle6_placer.geometry import ElementTransform
from eagle6_placer.parser import EagleBoardParser


def test_initial_fixtures_pass_audit(
    tangled_polish_brd: Path, mixed_tht_keepout_brd: Path
) -> None:
    """Both synthetic fixtures must start in a legally valid state."""
    for brd in (tangled_polish_brd, mixed_tht_keepout_brd):
        board = EagleBoardParser().parse(brd)
        checker = ConstraintChecker(board)
        violations = checker.audit_state(board.initial_state())
        assert violations == []


def test_keepout_and_hole_rejection(mixed_tht_keepout_brd: Path) -> None:
    """Top keepout rejects top SMDs (and THT) but allows bottom SMDs underneath."""
    board = EagleBoardParser().parse(mixed_tht_keepout_brd)
    checker = ConstraintChecker(board)
    state = board.initial_state()

    # Keepout is x=[24, 36], y=[28, 38] on layer 39 (top).
    # Top SMD C1 cannot be placed inside the top keepout.
    assert not checker.is_component_pose_valid(
        "C1", ElementTransform(30.0, 33.0, 0.0, mirrored=False), state
    )
    # Bottom SMD R1 CAN be placed directly under the top-only keepout.
    assert checker.is_component_pose_valid(
        "R1", ElementTransform(30.0, 33.0, 0.0, mirrored=True), state
    )
    # THT component L1 occupies both sides, so top keepout rejects it.
    assert not checker.is_component_pose_valid(
        "L1", ElementTransform(30.0, 33.0, 0.0, mirrored=False), state
    )
    # Board hole at (4, 4) drill 3.2mm rejects placement near (4, 4).
    assert not checker.is_component_pose_valid(
        "C1", ElementTransform(4.5, 4.5, 0.0, mirrored=False), state
    )


def test_opposite_side_smd_allowed_but_tht_blocks_both(
    mixed_tht_keepout_brd: Path,
) -> None:
    """Top and bottom SMDs may overlap in XY; THT blocks both sides."""
    board = EagleBoardParser().parse(mixed_tht_keepout_brd)
    checker = ConstraintChecker(board)
    state = board.initial_state()

    # Place top SMD C1 directly above bottom SMD R1 at (45, 34): legal!
    assert checker.is_component_pose_valid(
        "C1", ElementTransform(45.0, 34.0, 0.0, mirrored=False), state
    )

    # Place bottom SMD R1 onto THT L1 at (30, 14): illegal because L1 is THT!
    assert not checker.is_component_pose_valid(
        "R1", ElementTransform(30.0, 14.0, 0.0, mirrored=True), state
    )


def test_keep_side_and_locked_immutability(mixed_tht_keepout_brd: Path) -> None:
    """Keep-side mode rejects mirror flips; locked parts reject any move."""
    board = EagleBoardParser().parse(mixed_tht_keepout_brd)
    checker = ConstraintChecker(board, allow_mirror=False)
    state = board.initial_state()

    # Flipping C1 to bottom side must be rejected.
    assert not checker.is_component_pose_valid(
        "C1", ElementTransform(42.0, 10.0, 0.0, mirrored=True), state
    )
    # Moving locked connector J1 must be rejected.
    assert not checker.is_component_pose_valid(
        "J1", ElementTransform(8.0, 22.0, 0.0, mirrored=False), state
    )
