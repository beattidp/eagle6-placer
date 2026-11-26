"""Component name selection and range-expansion utilities for CLI flags.

Supports individual names, comma-separated lists, bash brace-expanded tokens,
and literal range expressions such as ``C1..C12`` or ``{C1..C12},{C20..C30}``.
"""

from __future__ import annotations

import re
from typing import Iterable

from eagle6_placer.models import BoardModel

# Matches a range token with matching alphabetic/symbolic prefix and numeric
# bounds, e.g. "C1..C12", "R01..R08", or "{C1..C12}".
_RANGE_RE = re.compile(
    r"^\{?(?P<p1>[A-Za-z_][A-Za-z0-9_]*?)(?P<n1>\d+)\.\.(?P<p2>[A-Za-z_][A-Za-z0-9_]*?)(?P<n2>\d+)\}?$"
)


def expand_part_specs(specs: Iterable[str] | None) -> set[str]:
    """Expand component name specs (commas, braces, numeric ranges) into names.

    Examples:
        - ``["U1,IC3"]`` -> ``{"U1", "IC3"}``
        - ``["{C1..C4},{C10..C11}"]`` -> ``{"C1", "C2", "C3", "C4", "C10", "C11"}``
        - ``["C1", "C2", "C3"]`` (bash-expanded) -> ``{"C1", "C2", "C3"}``
        - ``["R01..R03"]`` -> ``{"R01", "R02", "R03"}``
    """
    if not specs:
        return set()

    expanded: set[str] = set()
    for raw_arg in specs:
        # Split on commas or whitespace, stripping optional outer braces.
        for token in re.split(r"[\s,]+", raw_arg.strip()):
            if not token:
                continue
            match = _RANGE_RE.match(token)
            if match and match.group("p1") == match.group("p2"):
                prefix = match.group("p1")
                s1, s2 = match.group("n1"), match.group("n2")
                n1, n2 = int(s1), int(s2)
                pad_width = len(s1) if (s1.startswith("0") and len(s1) > 1) else 0
                step = 1 if n2 >= n1 else -1
                for idx in range(n1, n2 + step, step):
                    num_str = str(idx).zfill(pad_width) if pad_width else str(idx)
                    expanded.add(f"{prefix}{num_str}")
            else:
                cleaned = token.strip("{}")
                if cleaned:
                    expanded.add(cleaned)
    return expanded


def resolve_mirrorable_components(
    board: BoardModel,
    allow_mirror_enabled: bool,
    allow_specs: Iterable[str] | None = None,
    restrict_specs: Iterable[str] | None = None,
) -> frozenset[str]:
    """Resolve the exact set of unlocked SMD-only components allowed to mirror.

    Engineering rationale:
      - Locked components and through-hole (THT) packages are never eligible
        for automatic side flipping.
      - When ``allow_mirror_enabled`` is False, returns an empty set (keep-side).
      - When ``allow_mirror_enabled`` is True and ``allow_specs`` is empty,
        all unlocked SMD-only components are eligible unless excluded by
        ``restrict_specs``.
      - When ``allow_specs`` is non-empty, only matching unlocked SMD-only
        components (minus ``restrict_specs``) are eligible.
    """
    if not allow_mirror_enabled:
        return frozenset()

    eligible = {
        comp.name
        for comp in board.unlocked_components
        if not comp.footprint.is_through_hole
    }

    allowed = expand_part_specs(allow_specs)
    if allowed:
        eligible &= allowed

    restricted = expand_part_specs(restrict_specs)
    if restricted:
        eligible -= restricted

    return frozenset(eligible)
