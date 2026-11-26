"""Unit tests for the read-only CadSoft EAGLE v6.6.0 .brd XML parser."""

import math
from pathlib import Path

from eagle6_placer.parser import EagleBoardParser, parse_eagle_length_mm


def test_parse_eagle_length_units() -> None:
    """Verify unit conversion for mil, mm, inch, and um design rule values."""
    assert math.isclose(parse_eagle_length_mm("40mil"), 1.016, abs_tol=1e-6)
    assert math.isclose(parse_eagle_length_mm("0.5mm"), 0.5, abs_tol=1e-6)
    assert math.isclose(parse_eagle_length_mm("1inch"), 25.4, abs_tol=1e-6)
    assert math.isclose(parse_eagle_length_mm("250um"), 0.25, abs_tol=1e-6)


def test_parse_tangled_polish_fixture(tangled_polish_brd: Path) -> None:
    """Verify outline, design rules, locked/unlocked counts, and nets."""
    board = EagleBoardParser(courtyard_margin_mm=0.25).parse(tangled_polish_brd)

    assert board.eagle_version == "6.6.0"
    assert board.outline.is_axis_aligned_rect
    assert math.isclose(board.outline.bounds.width, 50.0)
    assert math.isclose(board.outline.bounds.height, 40.0)
    assert math.isclose(board.design_rules.edge_clearance_mm, 1.016, abs_tol=1e-6)

    assert len(board.components) == 9
    assert sorted(c.name for c in board.locked_components) == ["J1", "J2", "U1"]
    assert sorted(c.name for c in board.unlocked_components) == [
        "C1",
        "C2",
        "R1",
        "R2",
        "R3",
        "R4",
    ]
    assert board.routed_unlocked_components() == []
    assert len(board.nets) == 12


def test_parse_mixed_tht_keepout_fixture(mixed_tht_keepout_brd: Path) -> None:
    """Verify holes, keepouts, THT dual-side occupancy, bottom SMDs, and pours."""
    board = EagleBoardParser(courtyard_margin_mm=0.25).parse(mixed_tht_keepout_brd)

    assert len(board.holes) == 2
    assert len(board.keepouts) == 1
    assert board.keepouts[0].side == "top"
    assert board.keepouts[0].layer == 39

    # THT component L1 blocks both sides; R1/R2 are bottom-only SMDs.
    l1 = board.components["L1"]
    r1 = board.components["R1"]
    c1 = board.components["C1"]

    assert l1.footprint.is_through_hole
    assert l1.occupied_sides(l1.initial_pose) == ("top", "bottom")

    assert not r1.footprint.is_through_hole
    assert r1.initial_side == "bottom"
    assert r1.occupied_sides(r1.initial_pose) == ("bottom",)

    assert not c1.footprint.is_through_hole
    assert c1.initial_side == "top"
    assert c1.occupied_sides(c1.initial_pose) == ("top",)

    # GND net has a polygon copper pour; signal nets do not.
    assert board.nets["GND"].has_copper_pour is True
    assert board.nets["SIG1"].has_copper_pour is False
