"""Hard placement constraint checking for CadSoft EAGLE v6.6.0 boards.

All hard constraints are enforced as strict invariants during local polish
optimization:
  1. Locked components (``locked="yes"``) are strictly immobile.
  2. Components stay on their initial side unless ``allow_mirror=True``.
  3. Transformed courtyards remain inside the layer 20 outline minus edge
     clearance.
  4. Same-side courtyards never overlap (THT components occupy both sides).
  5. Courtyards avoid board-level mechanical ``<hole>`` primitives and
     same-side keepout/restrict regions.
"""

from __future__ import annotations

from dataclasses import dataclass

from eagle6_placer.geometry import ElementTransform, Rect2D
from eagle6_placer.models import BoardModel, Component, PlacementState


@dataclass(frozen=True)
class ConstraintViolation:
    """Description of a single hard-constraint violation."""

    kind: str
    component: str
    other: str | None = None
    detail: str = ""


class ConstraintChecker:
    """Validates individual moves and full board placement states."""

    def __init__(
        self,
        board: BoardModel,
        edge_clearance_mm: float | None = None,
        allow_mirror: bool = False,
        hole_clearance_mm: float = 0.25,
    ) -> None:
        self.board = board
        self.edge_clearance_mm = (
            board.design_rules.edge_clearance_mm
            if edge_clearance_mm is None
            else edge_clearance_mm
        )
        self.allow_mirror = allow_mirror
        self.hole_clearance_mm = hole_clearance_mm

    def _courtyard_conflicts_with_static(
        self, comp: Component, pose: ElementTransform, courtyard: Rect2D
    ) -> ConstraintViolation | None:
        """Check static board-level constraints (outline, holes, keepouts)."""
        if comp.is_locked and pose != comp.initial_pose:
            return ConstraintViolation(
                kind="locked_moved",
                component=comp.name,
                detail="Locked component cannot be moved or rotated",
            )

        if not self.allow_mirror and pose.mirrored != comp.initial_pose.mirrored:
            return ConstraintViolation(
                kind="side_changed",
                component=comp.name,
                detail="Mirroring is disabled in keep-side mode",
            )

        if not self.board.outline.contains_courtyard(
            courtyard, edge_clearance_mm=self.edge_clearance_mm
        ):
            return ConstraintViolation(
                kind="outside_board",
                component=comp.name,
                detail=(
                    f"Courtyard {courtyard} violates board outline with "
                    f"{self.edge_clearance_mm:.3f} mm edge clearance"
                ),
            )

        for hole in self.board.holes:
            if courtyard.overlaps_circle(
                hole.center, hole.radius_mm + self.hole_clearance_mm
            ):
                return ConstraintViolation(
                    kind="hole_overlap",
                    component=comp.name,
                    detail=f"Courtyard overlaps mechanical hole at {hole.center}",
                )

        sides = comp.occupied_sides(pose)
        for keepout in self.board.keepouts:
            if keepout.side in sides and courtyard.overlaps(keepout.bounds):
                return ConstraintViolation(
                    kind="keepout_overlap",
                    component=comp.name,
                    detail=(
                        f"Courtyard overlaps layer {keepout.layer} keepout "
                        f"on {keepout.side} side"
                    ),
                )

        return None

    def is_component_hard_valid(
        self, name: str, pose: ElementTransform
    ) -> bool:
        """Check absolute hard invariants (locked, keep-side, board outline).

        Used during soft overlap-legalization when the initial board already
        contains pre-existing courtyard/hole overlaps: components may never
        violate locked immutability, board side, or board outline boundaries.
        """
        comp = self.board.components[name]
        if comp.is_locked and pose != comp.initial_pose:
            return False
        if not self.allow_mirror and pose.mirrored != comp.initial_pose.mirrored:
            return False
        courtyard = comp.courtyard_at(pose)
        return self.board.outline.contains_courtyard(
            courtyard, edge_clearance_mm=self.edge_clearance_mm
        )

    def count_component_soft_violations(
        self,
        name: str,
        pose: ElementTransform,
        state: PlacementState,
        ignore_names: set[str] | None = None,
    ) -> int:
        """Count hole, keepout, and same-side courtyard overlaps for ``name``."""
        comp = self.board.components[name]
        courtyard = comp.courtyard_at(pose)
        sides = comp.occupied_sides(pose)
        count = 0

        for hole in self.board.holes:
            if courtyard.overlaps_circle(
                hole.center, hole.radius_mm + self.hole_clearance_mm
            ):
                count += 1

        for keepout in self.board.keepouts:
            if keepout.side in sides and courtyard.overlaps(keepout.bounds):
                count += 1

        skip = ignore_names or set()
        for other_name, other_comp in self.board.components.items():
            if other_name == name or other_name in skip:
                continue
            other_pose = state.poses[other_name]
            other_sides = other_comp.occupied_sides(other_pose)
            if not (sides[0] in other_sides or (len(sides) > 1 and sides[1] in other_sides)):
                continue
            if courtyard.overlaps(other_comp.courtyard_at(other_pose)):
                count += 1

        return count

    def is_component_pose_valid(
        self,
        name: str,
        pose: ElementTransform,
        state: PlacementState,
        ignore_names: set[str] | None = None,
    ) -> bool:
        """Fast boolean feasibility check for placing ``name`` at ``pose``."""
        if not self.is_component_hard_valid(name, pose):
            return False
        return (
            self.count_component_soft_violations(
                name, pose, state, ignore_names=ignore_names
            )
            == 0
        )

    def is_swap_valid(
        self,
        name_a: str,
        pose_a: ElementTransform,
        name_b: str,
        pose_b: ElementTransform,
        state: PlacementState,
    ) -> bool:
        """Validate a simultaneous pairwise swap of two unlocked components."""
        ignore = {name_a, name_b}
        if not self.is_component_pose_valid(name_a, pose_a, state, ignore_names=ignore):
            return False
        if not self.is_component_pose_valid(name_b, pose_b, state, ignore_names=ignore):
            return False

        comp_a = self.board.components[name_a]
        comp_b = self.board.components[name_b]
        sides_a = comp_a.occupied_sides(pose_a)
        sides_b = comp_b.occupied_sides(pose_b)
        if any(s in sides_b for s in sides_a):
            if comp_a.courtyard_at(pose_a).overlaps(comp_b.courtyard_at(pose_b)):
                return False
        return True

    def audit_state(self, state: PlacementState) -> list[ConstraintViolation]:
        """Run a comprehensive constraint audit over the entire board state."""
        violations: list[ConstraintViolation] = []
        names = sorted(self.board.components.keys())
        courtyards: dict[str, Rect2D] = {}
        sides_map: dict[str, tuple[str, ...]] = {}

        for name in names:
            comp = self.board.components[name]
            pose = state.poses[name]
            courtyard = comp.courtyard_at(pose)
            courtyards[name] = courtyard
            sides_map[name] = comp.occupied_sides(pose)

            if not comp.is_locked:
                static_err = self._courtyard_conflicts_with_static(comp, pose, courtyard)
                if static_err is not None:
                    violations.append(static_err)
            elif pose != comp.initial_pose:
                violations.append(
                    ConstraintViolation(
                        kind="locked_moved",
                        component=name,
                        detail="Locked component moved from initial pose",
                    )
                )

        # Pairwise courtyard overlap check (each pair checked once).
        for i, name_a in enumerate(names):
            comp_a = self.board.components[name_a]
            for name_b in names[i + 1 :]:
                comp_b = self.board.components[name_b]
                if comp_a.is_locked and comp_b.is_locked:
                    continue
                if not any(s in sides_map[name_b] for s in sides_map[name_a]):
                    continue
                if courtyards[name_a].overlaps(courtyards[name_b]):
                    violations.append(
                        ConstraintViolation(
                            kind="courtyard_overlap",
                            component=name_a,
                            other=name_b,
                            detail=f"Courtyards of {name_a} and {name_b} overlap",
                        )
                    )

        return violations
