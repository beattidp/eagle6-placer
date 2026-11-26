"""Unit tests for 2D geometry primitives and EAGLE v6 transforms."""

import math
import pytest

from eagle6_placer.geometry import (
    ElementTransform,
    Point2D,
    Rect2D,
    Segment2D,
    point_in_polygon,
    segments_properly_intersect,
)


@pytest.mark.parametrize(
    ("rot", "local_pt", "expected"),
    [
        ("R0", Point2D(2.0, 1.0), Point2D(12.0, 21.0)),
        ("R90", Point2D(2.0, 1.0), Point2D(9.0, 22.0)),
        ("R180", Point2D(2.0, 1.0), Point2D(8.0, 19.0)),
        ("R270", Point2D(2.0, 1.0), Point2D(11.0, 18.0)),
        # Mirror across local Y-axis (x -> -x) then CCW rotate:
        # (-2, 1) at MR0 -> (8, 21)
        ("MR0", Point2D(2.0, 1.0), Point2D(8.0, 21.0)),
        # (-2, 1) rotated CCW 90 -> (-1, -2) -> (9, 18)
        ("MR90", Point2D(2.0, 1.0), Point2D(9.0, 18.0)),
        # (-2, 1) rotated CCW 180 -> (2, -1) -> (12, 19)
        ("MR180", Point2D(2.0, 1.0), Point2D(12.0, 19.0)),
        # (-2, 1) rotated CCW 270 -> (1, 2) -> (11, 22)
        ("MR270", Point2D(2.0, 1.0), Point2D(11.0, 22.0)),
    ],
)
def test_element_transform_all_orthogonal_orientations(
    rot: str, local_pt: Point2D, expected: Point2D
) -> None:
    """Verify exact EAGLE v6 point transform for all 8 R*/MR* orientations."""
    tf = ElementTransform.from_eagle_rot(10.0, 20.0, rot)
    actual = tf.apply_point(local_pt)
    assert math.isclose(actual.x, expected.x, abs_tol=1e-6)
    assert math.isclose(actual.y, expected.y, abs_tol=1e-6)
    assert tf.to_eagle_rot() == rot


def test_element_transform_spin_preserved() -> None:
    """Spin flag (S) must round-trip without affecting copper geometry."""
    tf_spin = ElementTransform.from_eagle_rot(5.0, 5.0, "SR90")
    tf_plain = ElementTransform.from_eagle_rot(5.0, 5.0, "R90")
    pt = Point2D(1.0, -2.0)
    assert tf_spin.to_eagle_rot() == "SR90"
    assert tf_spin.apply_point(pt).distance_to(tf_plain.apply_point(pt)) < 1e-9


def test_rect_overlap_and_touching_edges() -> None:
    """Flush touching rectangles must not count as overlapping."""
    r1 = Rect2D(0.0, 0.0, 4.0, 4.0)
    r_touch = Rect2D(4.0, 0.0, 8.0, 4.0)
    r_overlap = Rect2D(3.5, 1.0, 8.0, 3.0)
    assert not r1.overlaps(r_touch)
    assert r1.overlaps(r_overlap)


def test_segments_properly_intersect() -> None:
    """Only strict interior crossings count; shared endpoints do not."""
    s1 = Segment2D(Point2D(0.0, 0.0), Point2D(4.0, 4.0))
    s2 = Segment2D(Point2D(0.0, 4.0), Point2D(4.0, 0.0))
    s_shared = Segment2D(Point2D(0.0, 0.0), Point2D(4.0, 0.0))
    s_parallel = Segment2D(Point2D(0.0, 1.0), Point2D(4.0, 5.0))

    assert segments_properly_intersect(s1, s2)
    assert not segments_properly_intersect(s1, s_shared)
    assert not segments_properly_intersect(s1, s_parallel)


def test_point_in_polygon_l_shape() -> None:
    """Verify ray-casting containment on a concave L-shaped outline."""
    l_poly = (
        Point2D(0.0, 0.0),
        Point2D(10.0, 0.0),
        Point2D(10.0, 5.0),
        Point2D(5.0, 5.0),
        Point2D(5.0, 10.0),
        Point2D(0.0, 10.0),
    )
    assert point_in_polygon(Point2D(2.0, 8.0), l_poly)
    assert point_in_polygon(Point2D(8.0, 2.0), l_poly)
    assert not point_in_polygon(Point2D(8.0, 8.0), l_poly)
