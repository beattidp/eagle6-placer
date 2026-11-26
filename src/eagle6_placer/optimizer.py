"""Local polish Simulated Annealing (SA) placement optimizer for EAGLE v6 boards.

Operates strictly on unlocked components (``locked != "yes"``) in keep-side
mode by default, enforcing zero hard-constraint violations at every accepted
step while minimizing pin-accurate MST wirelength, airwire crossings, and
optional displacement/proximity penalties.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from eagle6_placer.constraints import ConstraintChecker, ConstraintViolation
from eagle6_placer.cost import CostBreakdown, CostConfig, RoutabilityEvaluator
from eagle6_placer.geometry import ElementTransform, Point2D
from eagle6_placer.models import BoardModel, PlacementState

ORTHOGONAL_ANGLES: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)


class RoutedCopperError(RuntimeError):
    """Raised when unlocked components have existing routed copper and opt-in is off."""


@dataclass(frozen=True)
class PolishConfig:
    """Configuration for ``LocalPolishOptimizer``."""

    steps: int = 4000
    grid_mm: float = 0.5
    seed: int = 42
    t_start: float = 15.0
    t_end: float = 0.05
    max_nudge_mm: float | None = None
    allow_routed: bool = False
    ignore_pour_copper: bool = True
    allow_mirror: bool = False
    edge_clearance_mm: float | None = None
    cost_config: CostConfig = field(default_factory=CostConfig)


@dataclass
class OptimizationResult:
    """Complete record of an optimization run for reporting and script emission."""

    initial_state: PlacementState
    best_state: PlacementState
    initial_cost: CostBreakdown
    best_cost: CostBreakdown
    steps_executed: int
    accepted_moves: int
    feasible_proposals: int
    rejected_infeasible: int
    runtime_seconds: float
    seed: int
    final_violations: list[ConstraintViolation]


class LocalPolishOptimizer:
    """Simulated Annealing local placement polisher for CadSoft EAGLE v6 boards."""

    def __init__(
        self, board: BoardModel, config: PolishConfig | None = None
    ) -> None:
        self.board = board
        self.config = config or PolishConfig()
        self.checker = ConstraintChecker(
            board=board,
            edge_clearance_mm=self.config.edge_clearance_mm,
            allow_mirror=self.config.allow_mirror,
        )
        self.evaluator = RoutabilityEvaluator(
            board=board, config=self.config.cost_config
        )

    def optimize(self) -> OptimizationResult:
        """Run deterministic local polish SA and return the best feasible result."""
        t0 = time.perf_counter()

        routed_unlocked = self.board.routed_unlocked_components(
            ignore_pour_nets=self.config.ignore_pour_copper
        )
        if routed_unlocked and not self.config.allow_routed:
            raise RoutedCopperError(
                "Unlocked components have existing routed copper: "
                f"{', '.join(routed_unlocked)}. Rip up those nets first or "
                "pass --allow-routed to proceed anyway."
            )

        initial_state = self.board.initial_state()
        current_state = initial_state.copy()
        current_violations = len(self.checker.audit_state(initial_state))
        initial_cost = self.evaluator.evaluate(
            initial_state, overlap_violations=current_violations
        )
        current_cost = initial_cost

        best_state = initial_state.copy()
        best_cost = initial_cost
        best_violations = current_violations

        unlocked = [c.name for c in self.board.unlocked_components]
        if not unlocked or self.config.steps <= 0:
            elapsed = time.perf_counter() - t0
            return OptimizationResult(
                initial_state=initial_state,
                best_state=best_state,
                initial_cost=initial_cost,
                best_cost=best_cost,
                steps_executed=0,
                accepted_moves=0,
                feasible_proposals=0,
                rejected_infeasible=0,
                runtime_seconds=elapsed,
                seed=self.config.seed,
                final_violations=self.checker.audit_state(best_state),
            )

        # Group unlocked components by initial side for valid same-side swaps.
        by_side: dict[str, list[str]] = {"top": [], "bottom": []}
        for name in unlocked:
            by_side[self.board.components[name].initial_side].append(name)
        swappable_sides = [names for names in by_side.values() if len(names) >= 2]

        board_span = max(
            self.board.outline.bounds.width, self.board.outline.bounds.height
        )
        max_radius = (
            self.config.max_nudge_mm
            if self.config.max_nudge_mm is not None
            else max(2.0 * self.config.grid_mm, 0.35 * board_span)
        )
        min_radius = max(self.config.grid_mm, 0.5)

        rng = random.Random(self.config.seed)
        steps = self.config.steps
        t_start = max(self.config.t_start, 1e-6)
        t_end = max(min(self.config.t_end, t_start), 1e-6)
        cooling_ratio = t_end / t_start

        accepted = 0
        feasible = 0
        infeasible = 0

        for step in range(steps):
            progress = step / max(steps - 1, 1)
            temp = t_start * (cooling_ratio**progress)
            radius = max_radius * (1.0 - progress) + min_radius * progress

            move_roll = rng.random()

            if move_roll < 0.15 and swappable_sides:
                # Pairwise swap between two unlocked components on the same side.
                pool = rng.choice(swappable_sides)
                name_a, name_b = rng.sample(pool, 2)
                pose_a = current_state.poses[name_a]
                pose_b = current_state.poses[name_b]

                pt_a = Point2D(pose_b.x, pose_b.y).snapped(self.config.grid_mm)
                pt_b = Point2D(pose_a.x, pose_a.y).snapped(self.config.grid_mm)
                cand_a = ElementTransform(
                    x=pt_a.x,
                    y=pt_a.y,
                    angle_deg=pose_a.angle_deg,
                    mirrored=pose_a.mirrored,
                    spin=pose_a.spin,
                )
                cand_b = ElementTransform(
                    x=pt_b.x,
                    y=pt_b.y,
                    angle_deg=pose_b.angle_deg,
                    mirrored=pose_b.mirrored,
                    spin=pose_b.spin,
                )

                if current_violations == 0:
                    if not self.checker.is_swap_valid(
                        name_a, cand_a, name_b, cand_b, current_state
                    ):
                        infeasible += 1
                        continue
                    cand_violations = 0
                else:
                    if not (
                        self.checker.is_component_hard_valid(name_a, cand_a)
                        and self.checker.is_component_hard_valid(name_b, cand_b)
                    ):
                        infeasible += 1
                        continue
                    ignore = {name_a, name_b}
                    old_v = (
                        self.checker.count_component_soft_violations(
                            name_a, pose_a, current_state, ignore_names=ignore
                        )
                        + self.checker.count_component_soft_violations(
                            name_b, pose_b, current_state, ignore_names=ignore
                        )
                    )
                    new_v = (
                        self.checker.count_component_soft_violations(
                            name_a, cand_a, current_state, ignore_names=ignore
                        )
                        + self.checker.count_component_soft_violations(
                            name_b, cand_b, current_state, ignore_names=ignore
                        )
                    )
                    # Check mutual overlap between A and B at old vs new poses.
                    comp_a = self.board.components[name_a]
                    comp_b = self.board.components[name_b]
                    if any(
                        s in comp_b.occupied_sides(pose_b)
                        for s in comp_a.occupied_sides(pose_a)
                    ) and comp_a.courtyard_at(pose_a).overlaps(
                        comp_b.courtyard_at(pose_b)
                    ):
                        old_v += 1
                    if any(
                        s in comp_b.occupied_sides(cand_b)
                        for s in comp_a.occupied_sides(cand_a)
                    ) and comp_a.courtyard_at(cand_a).overlaps(
                        comp_b.courtyard_at(cand_b)
                    ):
                        new_v += 1
                    cand_violations = current_violations - old_v + new_v
                    if cand_violations > current_violations:
                        infeasible += 1
                        continue

                feasible += 1
                current_state.poses[name_a] = cand_a
                current_state.poses[name_b] = cand_b
                cand_cost = self.evaluator.evaluate(
                    current_state, overlap_violations=cand_violations
                )
                delta = cand_cost.total_cost - current_cost.total_cost

                if delta <= 0.0 or rng.random() < math.exp(-delta / temp):
                    current_cost = cand_cost
                    current_violations = cand_violations
                    accepted += 1
                    if cand_cost.total_cost < best_cost.total_cost:
                        best_cost = cand_cost
                        best_state = current_state.copy()
                        best_violations = cand_violations
                else:
                    current_state.poses[name_a] = pose_a
                    current_state.poses[name_b] = pose_b
            else:
                # Single-component move: nudge, rotate, or nudge + rotate.
                name = rng.choice(unlocked)
                old_pose = current_state.poses[name]
                cand_pose = self._propose_single_move(
                    old_pose, move_roll, radius, rng
                )
                if cand_pose == old_pose:
                    continue

                if current_violations == 0:
                    if not self.checker.is_component_pose_valid(
                        name, cand_pose, current_state
                    ):
                        infeasible += 1
                        continue
                    cand_violations = 0
                else:
                    if not self.checker.is_component_hard_valid(name, cand_pose):
                        infeasible += 1
                        continue
                    old_v = self.checker.count_component_soft_violations(
                        name, old_pose, current_state
                    )
                    new_v = self.checker.count_component_soft_violations(
                        name, cand_pose, current_state
                    )
                    cand_violations = current_violations - old_v + new_v
                    if cand_violations > current_violations:
                        infeasible += 1
                        continue

                feasible += 1
                current_state.poses[name] = cand_pose
                cand_cost = self.evaluator.evaluate(
                    current_state, overlap_violations=cand_violations
                )
                delta = cand_cost.total_cost - current_cost.total_cost

                if delta <= 0.0 or rng.random() < math.exp(-delta / temp):
                    current_cost = cand_cost
                    current_violations = cand_violations
                    accepted += 1
                    if cand_cost.total_cost < best_cost.total_cost:
                        best_cost = cand_cost
                        best_state = current_state.copy()
                        best_violations = cand_violations
                else:
                    current_state.poses[name] = old_pose

        # Final greedy orientation polish pass over every unlocked component
        # to eliminate any trivial residual 90-degree rotation suboptimality.
        best_state, best_cost = self._greedy_rotation_pass(
            best_state, best_cost, best_violations, unlocked
        )

        elapsed = time.perf_counter() - t0
        return OptimizationResult(
            initial_state=initial_state,
            best_state=best_state,
            initial_cost=initial_cost,
            best_cost=best_cost,
            steps_executed=steps,
            accepted_moves=accepted,
            feasible_proposals=feasible,
            rejected_infeasible=infeasible,
            runtime_seconds=elapsed,
            seed=self.config.seed,
            final_violations=self.checker.audit_state(best_state),
        )

    def _propose_single_move(
        self,
        pose: ElementTransform,
        move_roll: float,
        radius: float,
        rng: random.Random,
    ) -> ElementTransform:
        """Propose a grid-snapped nudge, 90° rotation, or combined move."""
        grid = self.config.grid_mm
        new_x, new_y = pose.x, pose.y
        new_angle = pose.angle_deg

        # Nudge component center if move is nudge (0.15..0.60) or nudge+rotate (0.80..1.0).
        if move_roll < 0.60 or move_roll >= 0.80:
            dx = rng.uniform(-radius, radius)
            dy = rng.uniform(-radius, radius)
            snapped = Point2D(pose.x + dx, pose.y + dy).snapped(grid)
            new_x, new_y = snapped.x, snapped.y

        # Rotate component if move is rotate (0.60..0.80) or nudge+rotate (0.80..1.0).
        if move_roll >= 0.60:
            other_angles = [
                a for a in ORTHOGONAL_ANGLES if abs(a - pose.angle_deg) > 1e-6
            ]
            new_angle = rng.choice(other_angles)

        return ElementTransform(
            x=new_x,
            y=new_y,
            angle_deg=new_angle,
            mirrored=pose.mirrored,
            spin=pose.spin,
        )

    def _greedy_rotation_pass(
        self,
        state: PlacementState,
        cost: CostBreakdown,
        violations: int,
        unlocked_names: list[str],
    ) -> tuple[PlacementState, CostBreakdown]:
        """Deterministic final pass testing all 4 orthogonal angles per part."""
        best_state = state.copy()
        best_cost = cost
        best_v = violations
        for name in unlocked_names:
            orig_pose = best_state.poses[name]
            best_pose = orig_pose
            for angle in ORTHOGONAL_ANGLES:
                if abs(angle - orig_pose.angle_deg) < 1e-6:
                    continue
                cand_pose = ElementTransform(
                    x=orig_pose.x,
                    y=orig_pose.y,
                    angle_deg=angle,
                    mirrored=orig_pose.mirrored,
                    spin=orig_pose.spin,
                )
                if best_v == 0:
                    if not self.checker.is_component_pose_valid(
                        name, cand_pose, best_state
                    ):
                        continue
                    cand_v = 0
                else:
                    if not self.checker.is_component_hard_valid(name, cand_pose):
                        continue
                    old_v = self.checker.count_component_soft_violations(
                        name, orig_pose, best_state
                    )
                    new_v = self.checker.count_component_soft_violations(
                        name, cand_pose, best_state
                    )
                    cand_v = best_v - old_v + new_v
                    if cand_v > best_v:
                        continue
                best_state.poses[name] = cand_pose
                cand_cost = self.evaluator.evaluate(
                    best_state, overlap_violations=cand_v
                )
                if cand_cost.total_cost < best_cost.total_cost - 1e-9:
                    best_cost = cand_cost
                    best_pose = cand_pose
                    best_v = cand_v
            best_state.poses[name] = best_pose
        return best_state, best_cost
