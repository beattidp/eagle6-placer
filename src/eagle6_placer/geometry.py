"""2D geometric primitives and CadSoft EAGLE v6 coordinate transforms.

All coordinates and dimensions throughout ``eagle6_placer`` use millimeters
(``mm``), matching CadSoft EAGLE v6.6.0's native XML storage unit.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

# EAGLE v6 rotation attribute pattern: optional M (mirror), optional S (spin),
# followed by R<angle_degrees>, e.g., "R0", "R90", "MR180", "SMR270".
_EAGLE_ROT_RE = re.compile(
    r"^(?P<mirror>M)?(?P<spin>S)?R(?P<angle>-?\d+(?:\.\d+)?)$"
)


@dataclass(frozen=True)
class Point2D:
    """Immutable 2D point in millimeters."""

    x: float
    y: float

    def distance_to(self, other: Point2D) -> float:
        """Return Euclidean distance in mm between this point and ``other``."""
        return math.hypot(self.x - other.x, self.y - other.y)

    def manhattan_to(self, other: Point2D) -> float:
        """Return Manhattan (L1) distance in mm between this point and ``other``."""
        return abs(self.x - other.x) + abs(self.y - other.y)

    def snapped(self, grid_mm: float) -> Point2D:
        """Snap coordinates to the nearest multiple of ``grid_mm``.

        If ``grid_mm <= 0``, returns the point unchanged.
        """
        if grid_mm <= 0.0:
            return self
        return Point2D(
            x=round(round(self.x / grid_mm) * grid_mm, 6),
            y=round(round(self.y / grid_mm) * grid_mm, 6),
        )


@dataclass(frozen=True)
class Rect2D:
    """Immutable axis-aligned 2D bounding box in millimeters."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        if self.min_x > self.max_x or self.min_y > self.max_y:
            raise ValueError(
                f"Invalid Rect2D bounds: ({self.min_x}, {self.min_y}) -> "
                f"({self.max_x}, {self.max_y})"
            )

    @property
    def width(self) -> float:
        """Return rectangle width in mm."""
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        """Return rectangle height in mm."""
        return self.max_y - self.min_y

    @property
    def center(self) -> Point2D:
        """Return the geometric center of the rectangle."""
        return Point2D(
            x=0.5 * (self.min_x + self.max_x),
            y=0.5 * (self.min_y + self.max_y),
        )

    def corners(self) -> tuple[Point2D, Point2D, Point2D, Point2D]:
        """Return the four corners in counter-clockwise order."""
        return (
            Point2D(self.min_x, self.min_y),
            Point2D(self.max_x, self.min_y),
            Point2D(self.max_x, self.max_y),
            Point2D(self.min_x, self.max_y),
        )

    def expanded(self, margin_mm: float) -> Rect2D:
        """Return a new rectangle expanded uniformly on all sides by ``margin_mm``."""
        return Rect2D(
            min_x=self.min_x - margin_mm,
            min_y=self.min_y - margin_mm,
            max_x=self.max_x + margin_mm,
            max_y=self.max_y + margin_mm,
        )

    def inset(self, margin_mm: float) -> Rect2D:
        """Return a new rectangle shrunk uniformly on all sides by ``margin_mm``."""
        new_min_x = self.min_x + margin_mm
        new_min_y = self.min_y + margin_mm
        new_max_x = self.max_x - margin_mm
        new_max_y = self.max_y - margin_mm
        if new_min_x > new_max_x or new_min_y > new_max_y:
            raise ValueError(
                f"Inset margin {margin_mm} mm collapses rectangle {self}"
            )
        return Rect2D(new_min_x, new_min_y, new_max_x, new_max_y)

    def overlaps(self, other: Rect2D, eps: float = 1e-9) -> bool:
        """Return True if ``self`` and ``other`` have positive-area overlap.

        Touching edges (within ``eps``) are NOT treated as overlaps so that
        adjacent courtyards placed flush on a grid remain legal.
        """
        return (
            self.min_x < other.max_x - eps
            and self.max_x > other.min_x + eps
            and self.min_y < other.max_y - eps
            and self.max_y > other.min_y + eps
        )

    def contains_rect(self, inner: Rect2D, eps: float = 1e-9) -> bool:
        """Return True if ``inner`` lies completely inside ``self``."""
        return (
            inner.min_x >= self.min_x - eps
            and inner.max_x <= self.max_x + eps
            and inner.min_y >= self.min_y - eps
            and inner.max_y <= self.max_y + eps
        )

    def overlaps_circle(self, center: Point2D, radius: float, eps: float = 1e-9) -> bool:
        """Return True if ``self`` overlaps an open disk of given center/radius."""
        closest_x = min(max(center.x, self.min_x), self.max_x)
        closest_y = min(max(center.y, self.min_y), self.max_y)
        dist_sq = (center.x - closest_x) ** 2 + (center.y - closest_y) ** 2
        effective_r = max(0.0, radius - eps)
        return dist_sq < effective_r * effective_r

    @classmethod
    def from_points(cls, points: Iterable[Point2D]) -> Rect2D:
        """Compute the minimal axis-aligned bounding box enclosing ``points``."""
        pts = list(points)
        if not pts:
            raise ValueError("Cannot build Rect2D from an empty point set")
        return cls(
            min_x=min(p.x for p in pts),
            min_y=min(p.y for p in pts),
            max_x=max(p.x for p in pts),
            max_y=max(p.y for p in pts),
        )

    @classmethod
    def union(cls, rects: Iterable[Rect2D]) -> Rect2D:
        """Compute the minimal bounding box enclosing all rectangles in ``rects``."""
        rect_list = list(rects)
        if not rect_list:
            raise ValueError("Cannot compute union of empty rectangle sequence")
        return cls(
            min_x=min(r.min_x for r in rect_list),
            min_y=min(r.min_y for r in rect_list),
            max_x=max(r.max_x for r in rect_list),
            max_y=max(r.max_y for r in rect_list),
        )


@dataclass(frozen=True)
class Segment2D:
    """Immutable 2D line segment defined by endpoints ``p1`` and ``p2``."""

    p1: Point2D
    p2: Point2D


@dataclass(frozen=True)
class ElementTransform:
    """Rigid 2D transform for a CadSoft EAGLE v6 board ``<element>``.

    Engineering rationale (EAGLE v6 transform convention):
    In CadSoft EAGLE v6 XML, an element's ``rot="[M][S]R<angle>"`` applies:
      1. Mirror across the package-local Y-axis (``x -> -x``) if ``mirrored``
         (``M`` prefix) is set, corresponding to mounting on the bottom side.
      2. Counter-clockwise rotation by ``angle_deg`` around the package origin.
      3. Translation by ``(x, y)`` to board coordinates.
    The optional ``S`` (spin) flag affects only silkscreen text uprightness
    and does not alter pad or courtyard geometry.
    """

    x: float
    y: float
    angle_deg: float = 0.0
    mirrored: bool = False
    spin: bool = False

    def __post_init__(self) -> None:
        # Normalize angle into [0, 360) for canonical comparisons and script output.
        normalized = self.angle_deg % 360.0
        if abs(normalized - 360.0) < 1e-9 or abs(normalized) < 1e-9:
            normalized = 0.0
        object.__setattr__(self, "angle_deg", normalized)

    @classmethod
    def from_eagle_rot(
        cls, x: float, y: float, rot: str | None = None
    ) -> ElementTransform:
        """Parse an EAGLE ``rot`` attribute string into an ``ElementTransform``."""
        if not rot:
            return cls(x=x, y=y, angle_deg=0.0, mirrored=False, spin=False)
        match = _EAGLE_ROT_RE.match(rot.strip())
        if not match:
            raise ValueError(f"Unsupported EAGLE rot specification: {rot!r}")
        return cls(
            x=x,
            y=y,
            angle_deg=float(match.group("angle")),
            mirrored=bool(match.group("mirror")),
            spin=bool(match.group("spin")),
        )

    def to_eagle_rot(self) -> str:
        """Format this transform's orientation as an EAGLE ``rot`` token."""
        prefix = ("M" if self.mirrored else "") + ("S" if self.spin else "")
        if abs(self.angle_deg - round(self.angle_deg)) < 1e-6:
            angle_str = str(int(round(self.angle_deg)) % 360)
        else:
            angle_str = f"{self.angle_deg:.3f}".rstrip("0").rstrip(".")
        return f"{prefix}R{angle_str}"

    def apply_point(self, pt: Point2D) -> Point2D:
        """Transform a package-local point into board coordinates (mm)."""
        lx = -pt.x if self.mirrored else pt.x
        ly = pt.y
        rad = math.radians(self.angle_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        bx = self.x + (lx * cos_a - ly * sin_a)
        by = self.y + (lx * sin_a + ly * cos_a)
        return Point2D(bx, by)

    def apply_rect(self, rect: Rect2D) -> Rect2D:
        """Transform a package-local bounding box into a board-space AABB."""
        transformed_corners = [self.apply_point(c) for c in rect.corners()]
        return Rect2D.from_points(transformed_corners)


def _orientation(a: Point2D, b: Point2D, c: Point2D) -> float:
    """Return signed 2D cross product (b - a) x (c - a)."""
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def segments_properly_intersect(
    s1: Segment2D, s2: Segment2D, eps: float = 1e-9
) -> bool:
    """Return True if segments ``s1`` and ``s2`` cross strictly in their interiors.

    Shared endpoints (such as two airwires meeting at the same pad) and
    collinear touching segments are NOT counted as crossings.
    """
    # Fast AABB rejection check before orientation predicates.
    if (
        max(s1.p1.x, s1.p2.x) < min(s2.p1.x, s2.p2.x) - eps
        or max(s2.p1.x, s2.p2.x) < min(s1.p1.x, s1.p2.x) - eps
        or max(s1.p1.y, s1.p2.y) < min(s2.p1.y, s2.p2.y) - eps
        or max(s2.p1.y, s2.p2.y) < min(s1.p1.y, s1.p2.y) - eps
    ):
        return False

    o1 = _orientation(s1.p1, s1.p2, s2.p1)
    o2 = _orientation(s1.p1, s1.p2, s2.p2)
    o3 = _orientation(s2.p1, s2.p2, s1.p1)
    o4 = _orientation(s2.p1, s2.p2, s1.p2)

    return ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and (
        (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
    )


def point_in_polygon(
    point: Point2D, polygon: Sequence[Point2D], eps: float = 1e-9
) -> bool:
    """Return True if ``point`` lies inside or on the boundary of ``polygon``.

    Uses the standard ray-casting algorithm with an explicit boundary distance
    check so points lying exactly on polygon edges count as contained.
    """
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        if point_to_segment_distance(point, Segment2D(a, b)) <= eps:
            return True
        if (a.y > point.y) != (b.y > point.y):
            x_intersect = a.x + (point.y - a.y) * (b.x - a.x) / (b.y - a.y)
            if point.x < x_intersect:
                inside = not inside
    return inside


def point_to_segment_distance(point: Point2D, segment: Segment2D) -> float:
    """Return the shortest Euclidean distance from ``point`` to ``segment``."""
    dx = segment.p2.x - segment.p1.x
    dy = segment.p2.y - segment.p1.y
    len_sq = dx * dx + dy * dy
    if len_sq <= 1e-18:
        return point.distance_to(segment.p1)
    t = ((point.x - segment.p1.x) * dx + (point.y - segment.p1.y) * dy) / len_sq
    t = min(1.0, max(0.0, t))
    proj = Point2D(segment.p1.x + t * dx, segment.p1.y + t * dy)
    return point.distance_to(proj)
