"""Unit tests for component name selection and range expansion."""

from pathlib import Path

from eagle6_placer.parser import EagleBoardParser
from eagle6_placer.selection import (
    expand_part_specs,
    resolve_mirrorable_components,
)


def test_expand_part_specs_commas_braces_and_ranges() -> None:
    """Verify comma lists, braced ranges, unbraced ranges, zero-padding, and bash lists."""
    assert expand_part_specs(["U1,IC3"]) == {"U1", "IC3"}
    assert expand_part_specs(["{C1..C3},{C10..C11}"]) == {
        "C1",
        "C2",
        "C3",
        "C10",
        "C11",
    }
    assert expand_part_specs(["R01..R03"]) == {"R01", "R02", "R03"}
    # Bash brace-expanded space-separated tokens
    assert expand_part_specs(["C1", "C2", "C3"]) == {"C1", "C2", "C3"}


def test_resolve_mirrorable_components(mixed_tht_keepout_brd: Path) -> None:
    """Verify opt-in mirroring excludes locked & THT parts and honors allow/restrict."""
    board = EagleBoardParser().parse(mixed_tht_keepout_brd)
    # Unlocked SMDs are C1, C2, R1, R2; L1 is unlocked THT; J1/J2 are locked THT.
    assert resolve_mirrorable_components(board, allow_mirror_enabled=False) == frozenset()

    # --allow-mirror with no args -> all unlocked SMDs, excluding THT L1.
    all_smd = resolve_mirrorable_components(board, allow_mirror_enabled=True)
    assert all_smd == frozenset({"C1", "C2", "R1", "R2"})

    # --allow-mirror '{C1..C2}' -> only C1, C2.
    caps_only = resolve_mirrorable_components(
        board, allow_mirror_enabled=True, allow_specs=["{C1..C2}"]
    )
    assert caps_only == frozenset({"C1", "C2"})

    # --allow-mirror --restrict-mirror R1,C2 -> only C1, R2.
    restricted = resolve_mirrorable_components(
        board, allow_mirror_enabled=True, restrict_specs=["R1,C2"]
    )
    assert restricted == frozenset({"C1", "R2"})
