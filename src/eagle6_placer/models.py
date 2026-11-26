"""Domain data models for CadSoft EAGLE v6.6.0 boards and placement state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from eagle6_placer.geometry import (
    ElementTransform,
    Point2D,
    Rect2D,
    Segment2D,
    point_in_polygon,
    point_to_segment_distance,
)

BoardSide = Literal["top", "bottom"]


@dataclass(frozen=True)
class Pin:
    """A single copper pad or SMD contact within a package footprint."""

    name: str
    position: Point2D
    is_through_hole: bool


@dataclass(frozen=True)
class Footprint:
    """Package geometry and courtyard definition in package-local coordinates.

    Attributes:
        library: Source EAGLE library name.
        name: EAGLE package name.
        pins: Mapping from pad/SMD name to local ``Pin``.
        local_courtyard: Axis-aligned package-local courtyard bounding box (mm).
        is_through_hole: True if the package contains any THT ``<pad>`` or
            ``<hole>``; THT parts occupy both top and bottom placement sides.
        courtyard_source: Provenance string (``"keepout"`` or ``"fallback"``).
    """

    library: str
    name: str
    pins: dict[str, Pin]
    local_courtyard: Rect2D
    is_through_hole: bool
    courtyard_source: str = "fallback"

    @property
    def key(self) -> tuple[str, str]:
        """Return unique ``(library, package)`` identifier."""
        return (self.library, self.name)


@dataclass(frozen=True)
class Component:
    """A board ``<element>`` instance referencing a ``Footprint``."""

    name: str
    value: str
    footprint: Footprint
    initial_pose: ElementTransform
    is_locked: bool

    @property
    def initial_side(self) -> BoardSide:
        """Return the component's initial mounting side."""
        return "bottom" if self.initial_pose.mirrored else "top"

    def occupied_sides(self, pose: ElementTransform) -> tuple[BoardSide, ...]:
        """Return the board side(s) physically blocked by this component."""
        if self.footprint.is_through_hole:
            return ("top", "bottom")
        return ("bottom",) if pose.mirrored else ("top",)

    def courtyard_at(self, pose: ElementTransform) -> Rect2D:
        """Return the component's board-space courtyard AABB at ``pose``."""
        return pose.apply_rect(self.footprint.local_courtyard)

    def pin_position(self, pin_name: str, pose: ElementTransform) -> Point2D:
        """Return the board-space center of ``pin_name`` at ``pose``."""
        pin = self.footprint.pins[pin_name]
        return pose.apply_point(pin.position)


@dataclass(frozen=True)
class ContactRef:
    """Reference to a specific pin on a named component."""

    component_name: str
    pin_name: str


@dataclass(frozen=True)
class Net:
    """An electrical ``<signal>`` connecting component pins."""

    name: str
    contacts: tuple[ContactRef, ...]
    has_routed_copper: bool = False
    has_copper_pour: bool = False


@dataclass(frozen=True)
class KeepoutRegion:
    """A board-level keepout or restrict region on a specific side."""

    bounds: Rect2D
    side: BoardSide
    layer: int


@dataclass(frozen=True)
class BoardHole:
    """A board-level mechanical drill hole in ``<plain>`` (blocks both sides)."""

    center: Point2D
    drill_mm: float

    @property
    def radius_mm(self) -> float:
        """Return drill radius in mm."""
        return 0.5 * self.drill_mm


@dataclass(frozen=True)
class DesignRules:
    """Subset of EAGLE ``<designrules>`` relevant to component placement."""

    name: str = "default"
    edge_clearance_mm: float = 0.5


@dataclass(frozen=True)
class BoardOutline:
    """Board perimeter extracted from layer 20 (``Dimension``).

    Supports both fast-path axis-aligned rectangular boards and arbitrary
    closed polygonal outlines.
    """

    bounds: Rect2D
    polygon: tuple[Point2D, ...] | None = None
    is_axis_aligned_rect: bool = True

    def contains_courtyard(
        self, courtyard: Rect2D, edge_clearance_mm: float = 0.0, eps: float = 1e-9
    ) -> bool:
        """Return True if ``courtyard`` stays inside the outline minus clearance."""
        if self.is_axis_aligned_rect or not self.polygon:
            try:
                safe_rect = self.bounds.inset(edge_clearance_mm)
            except ValueError:
                return False
            return safe_rect.contains_rect(courtyard, eps=eps)

        # General polygon containment: all 4 courtyard corners must lie inside
        # the polygon and maintain >= edge_clearance_mm from every outline edge.
        corners = courtyard.corners()
        poly = self.polygon
        n = len(poly)
        for corner in corners:
            if not point_in_polygon(corner, poly, eps=eps):
                return False
            if edge_clearance_mm > 0.0:
                for i in range(n):
                    seg = Segment2D(poly[i], poly[(i + 1) % n])
                    if point_to_segment_distance(corner, seg) < edge_clearance_mm - eps:
                        return False
        return True


@dataclass(frozen=True)
class BoardModel:
    """Complete read-only representation of a CadSoft EAGLE v6.6.0 ``.brd`` file."""

    source_path: Path
    eagle_version: str
    outline: BoardOutline
    design_rules: DesignRules
    components: dict[str, Component]
    nets: dict[str, Net]
    keepouts: tuple[KeepoutRegion, ...] = ()
    holes: tuple[BoardHole, ...] = ()

    @property
    def locked_components(self) -> list[Component]:
        """Return all immobile (``locked="yes"``) components."""
        return [c for c in self.components.values() if c.is_locked]

    @property
    def unlocked_components(self) -> list[Component]:
        """Return all movable (``locked != "yes"``) components."""
        return [c for c in self.components.values() if not c.is_locked]

    def routed_unlocked_components(self) -> list[str]:
        """Return sorted names of unlocked components attached to routed nets."""
        routed_names: set[str] = set()
        for net in self.nets.values():
            if not net.has_routed_copper:
                continue
            for ref in net.contacts:
                comp = self.components.get(ref.component_name)
                if comp is not None and not comp.is_locked:
                    routed_names.add(comp.name)
        return sorted(routed_names)

    def initial_state(self) -> PlacementState:
        """Create the initial ``PlacementState`` matching the parsed ``.brd``."""
        return PlacementState(
            poses={name: comp.initial_pose for name, comp in self.components.items()}
        )


@dataclass
class PlacementState:
    """Mutable mapping of component name -> board pose during optimization."""

    poses: dict[str, ElementTransform] = field(default_factory=dict)

    def copy(self) -> PlacementState:
        """Return a shallow copy of the pose dictionary (poses are immutable)."""
        return PlacementState(poses=dict(self.poses))
