"""Pin-accurate routability cost function for EAGLE v6 placement optimization.

Objective function:
    J(P) = w_wl * L_MST(P) + w_cross * C_airwire(P)
         + w_disp * D_anchor(P) + w_prox * G_prox(P)

Engineering rationale:
  - Pad-level Euclidean MST (Prim's algorithm) accurately reflects rotation
    effects on 2-pin passives and multi-pin ICs (unlike center-to-center HPWL).
  - Global copper-pour nets (GND, VCC, or nets with <polygon> pours / high
    fanout) are down-weighted and excluded from crossing penalties so power
    pours do not pull signal components off their natural routing paths.
  - Proper 2D segment intersections between MST airwires of distinct signal
    nets directly penalize routing tangles and via pressure.
"""

from __future__ import annotations

from dataclasses import dataclass

from eagle6_placer.geometry import Point2D, Segment2D, segments_properly_intersect
from eagle6_placer.models import BoardModel, Net, PlacementState

DEFAULT_POUR_NET_NAMES: tuple[str, ...] = (
    "GND",
    "AGND",
    "DGND",
    "PGND",
    "SGND",
    "VCC",
    "VDD",
    "VSS",
    "AVCC",
    "DVCC",
    "3V3",
    "3.3V",
    "+3V3",
    "+3.3V",
    "5V",
    "+5V",
    "12V",
    "+12V",
    "VIN",
    "VBUS",
)


@dataclass(frozen=True)
class CostConfig:
    """Tunable weights and net-classification parameters for ``RoutabilityEvaluator``."""

    wirelength_weight: float = 1.0
    crossing_weight: float = 5.0
    displacement_weight: float = 0.1
    proximity_weight: float = 2.0
    pour_net_weight: float = 0.05
    overlap_penalty_weight: float = 250.0
    high_fanout_threshold: int = 12
    pour_net_names: tuple[str, ...] = DEFAULT_POUR_NET_NAMES
    proximity_groups: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class CostBreakdown:
    """Decomposed placement cost metrics for reporting and optimization."""

    total_cost: float
    weighted_mst_wirelength_mm: float
    raw_mst_wirelength_mm: float
    airwire_crossings: int
    total_displacement_mm: float
    proximity_penalty_mm: float
    overlap_violations: int = 0


def compute_euclidean_mst(points: list[Point2D]) -> tuple[float, list[Segment2D]]:
    """Compute exact Euclidean Minimum Spanning Tree using Prim's algorithm.

    Returns ``(total_length_mm, edges)``. Complexity is O(k^2) for a net with
    k pins, which is optimal for small-to-medium PCB nets without heap overhead.
    """
    n = len(points)
    if n < 2:
        return 0.0, []
    if n == 2:
        d = points[0].distance_to(points[1])
        return d, [Segment2D(points[0], points[1])]

    in_tree = [False] * n
    min_dist = [float("inf")] * n
    parent = [-1] * n
    min_dist[0] = 0.0

    total_len = 0.0
    edges: list[Segment2D] = []

    for _ in range(n):
        u = -1
        best = float("inf")
        for i in range(n):
            if not in_tree[i] and min_dist[i] < best:
                best = min_dist[i]
                u = i
        if u == -1:
            break
        in_tree[u] = True
        if parent[u] != -1:
            total_len += best
            edges.append(Segment2D(points[parent[u]], points[u]))

        pu = points[u]
        for v in range(n):
            if not in_tree[v]:
                d = pu.distance_to(points[v])
                if d < min_dist[v]:
                    min_dist[v] = d
                    parent[v] = u

    return total_len, edges


class RoutabilityEvaluator:
    """Evaluates the scalar routability cost of a ``PlacementState``."""

    def __init__(self, board: BoardModel, config: CostConfig | None = None) -> None:
        self.board = board
        self.config = config or CostConfig()
        self._pour_names_upper = {n.upper() for n in self.config.pour_net_names}
        self._net_weights: dict[str, float] = {}
        self._signal_nets: list[Net] = []

        for net in board.nets.values():
            if len(net.contacts) < 2:
                continue
            is_pour = self._is_pour_or_global_net(net)
            self._net_weights[net.name] = (
                self.config.pour_net_weight if is_pour else 1.0
            )
            self._signal_nets.append(net)

        self._unlocked_names = [c.name for c in board.unlocked_components]

    def _is_pour_or_global_net(self, net: Net) -> bool:
        """Return True if ``net`` should be down-weighted as a pour/global net."""
        if net.has_copper_pour:
            return True
        if len(net.contacts) >= self.config.high_fanout_threshold:
            return True
        return net.name.upper() in self._pour_names_upper

    def is_pour_net(self, net_name: str) -> bool:
        """Public helper reporting whether ``net_name`` is treated as a pour net."""
        net = self.board.nets.get(net_name)
        if net is None:
            return False
        return self._is_pour_or_global_net(net)

    def evaluate(
        self, state: PlacementState, overlap_violations: int = 0
    ) -> CostBreakdown:
        """Compute the full ``CostBreakdown`` for ``state``."""
        weighted_wl = 0.0
        raw_wl = 0.0
        # Store (net_name, segment) for non-pour nets to count airwire crossings.
        non_pour_edges: list[tuple[str, Segment2D]] = []

        components = self.board.components
        poses = state.poses

        for net in self._signal_nets:
            pts: list[Point2D] = []
            for ref in net.contacts:
                comp = components.get(ref.component_name)
                if comp is None or ref.pin_name not in comp.footprint.pins:
                    continue
                pts.append(comp.pin_position(ref.pin_name, poses[ref.component_name]))

            if len(pts) < 2:
                continue

            mst_len, edges = compute_euclidean_mst(pts)
            weight = self._net_weights[net.name]
            raw_wl += mst_len
            weighted_wl += weight * mst_len

            if weight >= 1.0 - 1e-9:
                for edge in edges:
                    non_pour_edges.append((net.name, edge))

        crossings = 0
        num_edges = len(non_pour_edges)
        for i in range(num_edges):
            net_i, seg_i = non_pour_edges[i]
            for j in range(i + 1, num_edges):
                net_j, seg_j = non_pour_edges[j]
                if net_i == net_j:
                    continue
                if segments_properly_intersect(seg_i, seg_j):
                    crossings += 1

        displacement = 0.0
        for name in self._unlocked_names:
            init_pose = components[name].initial_pose
            curr_pose = poses[name]
            displacement += Point2D(init_pose.x, init_pose.y).distance_to(
                Point2D(curr_pose.x, curr_pose.y)
            )

        prox_penalty = 0.0
        for group in self.config.proximity_groups:
            group_pts = [
                Point2D(poses[name].x, poses[name].y)
                for name in group
                if name in poses
            ]
            if len(group_pts) >= 2:
                g_len, _ = compute_euclidean_mst(group_pts)
                prox_penalty += g_len

        total = (
            self.config.wirelength_weight * weighted_wl
            + self.config.crossing_weight * crossings
            + self.config.displacement_weight * displacement
            + self.config.proximity_weight * prox_penalty
            + self.config.overlap_penalty_weight * overlap_violations
        )
        return CostBreakdown(
            total_cost=total,
            weighted_mst_wirelength_mm=weighted_wl,
            raw_mst_wirelength_mm=raw_wl,
            airwire_crossings=crossings,
            total_displacement_mm=displacement,
            proximity_penalty_mm=prox_penalty,
            overlap_violations=overlap_violations,
        )
