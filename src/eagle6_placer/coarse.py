"""Coarse-to-fine analytical placement and grid-snapped overlap legalization.

Designed for boards whose unlocked components start outside the layer 20
board outline (e.g., freshly generated from CadSoft EAGLE Schematic -> Board)
or are badly scattered.

Pipeline:
  1. Force-directed spring relaxation around immobile ``locked="yes"`` anchors
     with short-range overlap repulsion and board-boundary clamping.
  2. Descending-area spiral grid legalization placing largest footprints first
     into strictly legal, non-overlapping positions.
  3. Downstream Simulated Annealing refinement via ``LocalPolishOptimizer``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from eagle6_placer.constraints import ConstraintChecker
from eagle6_placer.cost import CostConfig, RoutabilityEvaluator
from eagle6_placer.geometry import ElementTransform, Point2D
from eagle6_placer.models import BoardModel, PlacementState

ORTHOGONAL_ANGLES: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)


@dataclass(frozen=True)
class CoarseConfig:
    """Parameters for ``CoarsePlacer``."""

    grid_mm: float = 0.5
    seed: int = 42
    spring_iterations: int = 120
    edge_clearance_mm: float | None = None
    allow_mirror: bool = False
    mirrorable_names: frozenset[str] | None = None
    cost_config: CostConfig = CostConfig()


class CoarsePlacer:
    """Force-directed initial placer + area-ordered spiral overlap legalizer."""

    def __init__(
        self, board: BoardModel, config: CoarseConfig | None = None
    ) -> None:
        self.board = board
        self.config = config or CoarseConfig()
        self.checker = ConstraintChecker(
            board=board,
            edge_clearance_mm=self.config.edge_clearance_mm,
            allow_mirror=self.config.allow_mirror,
            mirrorable_names=self.config.mirrorable_names,
        )
        self.evaluator = RoutabilityEvaluator(board, self.config.cost_config)

    def place_coarse(self) -> PlacementState:
        """Compute a legalized coarse ``PlacementState`` inside the board outline."""
        unlocked = self.board.unlocked_components
        if not unlocked:
            return self.board.initial_state()

        targets = self._force_directed_targets()
        return self._legalize_spiral(targets)

    def _safe_board_rect(self) -> tuple[float, float, float, float]:
        """Return ``(min_x, min_y, max_x, max_y)`` inset by edge clearance."""
        b = self.board.outline.bounds
        edge = self.checker.edge_clearance_mm
        min_x = min(b.min_x + edge, b.center.x)
        max_x = max(b.max_x - edge, b.center.x)
        min_y = min(b.min_y + edge, b.center.y)
        max_y = max(b.max_y - edge, b.center.y)
        return min_x, min_y, max_x, max_y

    def _force_directed_targets(self) -> dict[str, Point2D]:
        """Run damped spring relaxation around locked anchors."""
        rng = random.Random(self.config.seed)
        min_x, min_y, max_x, max_y = self._safe_board_rect()
        cx = 0.5 * (min_x + max_x)
        cy = 0.5 * (min_y + max_y)

        # Build weighted neighbor graph (clique model for nets + proximity groups).
        adj: dict[str, dict[str, float]] = {
            name: {} for name in self.board.components
        }
        for net in self.board.nets.values():
            comp_names = sorted({ref.component_name for ref in net.contacts if ref.component_name in self.board.components})
            k = len(comp_names)
            if k < 2:
                continue
            net_w = (
                self.config.cost_config.pour_net_weight
                if self.evaluator.is_pour_net(net.name)
                else 1.0
            )
            edge_w = net_w / max(k - 1, 1)
            for i in range(k):
                u = comp_names[i]
                for j in range(i + 1, k):
                    v = comp_names[j]
                    adj[u][v] = adj[u].get(v, 0.0) + edge_w
                    adj[v][u] = adj[v].get(u, 0.0) + edge_w

        for group in self.config.cost_config.proximity_groups:
            valid = [n for n in group if n in self.board.components]
            for i in range(len(valid)):
                for j in range(i + 1, len(valid)):
                    u, v = valid[i], valid[j]
                    w = self.config.cost_config.proximity_weight
                    adj[u][v] = adj[u].get(v, 0.0) + w
                    adj[v][u] = adj[v].get(u, 0.0) + w

        # Initialize coordinates: locked fixed, unlocked inside board with slight jitter.
        pos: dict[str, list[float]] = {}
        half_dims: dict[str, tuple[float, float]] = {}
        for name, comp in self.board.components.items():
            rect = comp.courtyard_at(comp.initial_pose)
            half_dims[name] = (0.5 * rect.width, 0.5 * rect.height)
            if comp.is_locked:
                pos[name] = [comp.initial_pose.x, comp.initial_pose.y]
            else:
                ix, iy = comp.initial_pose.x, comp.initial_pose.y
                in_bounds = (min_x <= ix <= max_x) and (min_y <= iy <= max_y)
                if in_bounds:
                    pos[name] = [ix, iy]
                else:
                    pos[name] = [
                        cx + rng.uniform(-2.0, 2.0),
                        cy + rng.uniform(-2.0, 2.0),
                    ]

        unlocked_names = [c.name for c in self.board.unlocked_components]
        iters = max(1, self.config.spring_iterations)

        for step in range(iters):
            alpha = 0.45 * (1.0 - step / iters) + 0.05
            new_pos: dict[str, list[float]] = {}

            for name in unlocked_names:
                neighbors = adj[name]
                x_cur, y_cur = pos[name]

                # Attractive spring equilibrium toward weighted neighbor centroid.
                if neighbors:
                    w_sum = sum(neighbors.values())
                    tx = sum(w * pos[nb][0] for nb, w in neighbors.items()) / w_sum
                    ty = sum(w * pos[nb][1] for nb, w in neighbors.items()) / w_sum
                else:
                    tx, ty = cx, cy

                nx = x_cur + alpha * (tx - x_cur)
                ny = y_cur + alpha * (ty - y_cur)

                # Short-range repulsion from other nearby components to spread clusters.
                hw, hh = half_dims[name]
                for other_name in self.board.components:
                    if other_name == name:
                        continue
                    ox, oy = pos[other_name]
                    ohw, ohh = half_dims[other_name]
                    dx = nx - ox
                    dy = ny - oy
                    min_sep_x = hw + ohw
                    min_sep_y = hh + ohh
                    if abs(dx) < min_sep_x and abs(dy) < min_sep_y:
                        dist = math.hypot(dx, dy)
                        if dist < 1e-4:
                            angle = rng.uniform(0.0, 2.0 * math.pi)
                            dx, dy, dist = math.cos(angle), math.sin(angle), 1.0
                        push = 0.25 * alpha
                        nx += push * (dx / dist) * (min_sep_x - abs(dx) + 0.5)
                        ny += push * (dy / dist) * (min_sep_y - abs(dy) + 0.5)

                # Clamp inside board outline minus component half-size.
                lo_x = min(min_x + hw, cx)
                hi_x = max(max_x - hw, cx)
                lo_y = min(min_y + hh, cy)
                hi_y = max(max_y - hh, cy)
                nx = min(hi_x, max(lo_x, nx))
                ny = min(hi_y, max(lo_y, ny))
                new_pos[name] = [nx, ny]

            for name, xy in new_pos.items():
                pos[name] = xy

        return {name: Point2D(pos[name][0], pos[name][1]) for name in unlocked_names}

    def _legalize_spiral(self, targets: dict[str, Point2D]) -> PlacementState:
        """Place unlocked components largest-first onto legal grid-snapped poses."""
        grid = max(self.config.grid_mm, 0.25)
        state = PlacementState(
            poses={
                c.name: c.initial_pose for c in self.board.locked_components
            }
        )
        placed_names: set[str] = set(state.poses.keys())

        # Sort unlocked components by descending courtyard area (largest ICs first).
        unlocked_sorted = sorted(
            self.board.unlocked_components,
            key=lambda c: (
                -(c.footprint.local_courtyard.width * c.footprint.local_courtyard.height),
                c.name,
            ),
        )

        board_span = max(
            self.board.outline.bounds.width, self.board.outline.bounds.height
        )
        max_ring = int(math.ceil(board_span / grid)) + 2
        all_names = set(self.board.components.keys())

        for comp in unlocked_sorted:
            target = targets[comp.name].snapped(grid)
            unplaced_ignore = all_names - placed_names - {comp.name}
            can_mirror = self.checker.can_mirror_component(comp)
            side_order = (
                (comp.initial_pose.mirrored, not comp.initial_pose.mirrored)
                if can_mirror
                else (comp.initial_pose.mirrored,)
            )
            # Prefer initial angle first, then remaining orthogonal angles.
            angles = (comp.initial_pose.angle_deg,) + tuple(
                a for a in ORTHOGONAL_ANGLES if abs(a - comp.initial_pose.angle_deg) > 1e-6
            )

            chosen_pose: ElementTransform | None = None
            fallback_pose: ElementTransform | None = None
            fallback_violations = 10**9

            for ring in range(max_ring):
                offsets = self._ring_offsets(ring)
                for dx_i, dy_i in offsets:
                    cand_pt = Point2D(
                        target.x + dx_i * grid, target.y + dy_i * grid
                    ).snapped(grid)
                    for mirrored in side_order:
                        for angle in angles:
                            cand = ElementTransform(
                                x=cand_pt.x,
                                y=cand_pt.y,
                                angle_deg=angle,
                                mirrored=mirrored,
                                spin=comp.initial_pose.spin,
                            )
                            if not self.checker.is_component_hard_valid(comp.name, cand):
                                continue
                            v = self.checker.count_component_soft_violations(
                                comp.name, cand, state, ignore_names=unplaced_ignore
                            )
                            if v == 0:
                                chosen_pose = cand
                                break
                            if v < fallback_violations:
                                fallback_violations = v
                                fallback_pose = cand
                        if chosen_pose is not None:
                            break
                    if chosen_pose is not None:
                        break
                if chosen_pose is not None:
                    break

            state.poses[comp.name] = (
                chosen_pose
                if chosen_pose is not None
                else (fallback_pose if fallback_pose is not None else comp.initial_pose)
            )
            placed_names.add(comp.name)

        return state

    @staticmethod
    def _ring_offsets(ring: int) -> list[tuple[int, int]]:
        """Return integer grid offsets on Chebyshev ring ``ring``."""
        if ring == 0:
            return [(0, 0)]
        pts: list[tuple[int, int]] = []
        for dx in range(-ring, ring + 1):
            pts.append((dx, ring))
            pts.append((dx, -ring))
        for dy in range(-ring + 1, ring):
            pts.append((ring, dy))
            pts.append((-ring, dy))
        return pts
