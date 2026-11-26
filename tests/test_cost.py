"""Unit tests for Prim's MST wirelength and routability cost evaluation."""

import math
from pathlib import Path

from eagle6_placer.cost import CostConfig, RoutabilityEvaluator, compute_euclidean_mst
from eagle6_placer.geometry import Point2D
from eagle6_placer.parser import EagleBoardParser


def test_euclidean_mst_square() -> None:
    """MST of a unit square has 3 edges of length 1.0 (total 3.0)."""
    pts = [
        Point2D(0.0, 0.0),
        Point2D(1.0, 0.0),
        Point2D(1.0, 1.0),
        Point2D(0.0, 1.0),
    ]
    total, edges = compute_euclidean_mst(pts)
    assert len(edges) == 3
    assert math.isclose(total, 3.0, abs_tol=1e-6)


def test_pour_net_detection_and_initial_cost(
    tangled_polish_brd: Path, mixed_tht_keepout_brd: Path
) -> None:
    """Verify pour-net classification and positive crossing count on tangled board."""
    board_tangled = EagleBoardParser().parse(tangled_polish_brd)
    eval_tangled = RoutabilityEvaluator(board_tangled, CostConfig())
    assert eval_tangled.is_pour_net("GND")
    assert eval_tangled.is_pour_net("VCC")
    assert not eval_tangled.is_pour_net("IN_A")

    cost = eval_tangled.evaluate(board_tangled.initial_state())
    assert cost.weighted_mst_wirelength_mm > 0.0
    assert cost.raw_mst_wirelength_mm > cost.weighted_mst_wirelength_mm
    assert cost.airwire_crossings >= 2
    assert math.isclose(cost.total_displacement_mm, 0.0, abs_tol=1e-9)

    board_mixed = EagleBoardParser().parse(mixed_tht_keepout_brd)
    eval_mixed = RoutabilityEvaluator(board_mixed, CostConfig())
    assert eval_mixed.is_pour_net("GND")
    assert not eval_mixed.is_pour_net("SIG1")


def test_congestion_grid_penalizes_bottleneck(tangled_polish_brd: Path) -> None:
    """Congestion grid must report positive penalty on clustered tangles and 0 when disabled."""
    board = EagleBoardParser().parse(tangled_polish_brd)
    state = board.initial_state()

    eval_on = RoutabilityEvaluator(
        board,
        CostConfig(
            congestion_weight=1.0,
            congestion_cell_mm=5.0,
            congestion_capacity=1.0,
        ),
    )
    eval_off = RoutabilityEvaluator(
        board,
        CostConfig(congestion_weight=0.0),
    )

    c_on = eval_on.evaluate(state)
    c_off = eval_off.evaluate(state)
    assert c_on.congestion_penalty > 0.0
    assert c_off.congestion_penalty == 0.0
    assert c_on.total_cost > c_off.total_cost
