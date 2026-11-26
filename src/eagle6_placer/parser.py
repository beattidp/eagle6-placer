"""Read-only XML parser for CadSoft EAGLE v6.6.0 ``.brd`` files.

Safety invariant: this module strictly reads ``.brd`` XML from disk and never
writes or mutates board or schematic files.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from eagle6_placer.geometry import ElementTransform, Point2D, Rect2D
from eagle6_placer.models import (
    BoardHole,
    BoardModel,
    BoardOutline,
    BoardSide,
    Component,
    ContactRef,
    DesignRules,
    Footprint,
    KeepoutRegion,
    Net,
    Pin,
)

# EAGLE layer numbers used for placement geometry extraction.
LAYER_DIMENSION = 20
LAYER_TPLACE = 21
LAYER_BPLACE = 22
LAYER_TKEEPOUT = 39
LAYER_BKEEPOUT = 40
LAYER_TRESTRICT = 41
LAYER_BRESTRICT = 42

_UNIT_VALUE_RE = re.compile(
    r"^\s*(?P<num>-?\d+(?:\.\d+)?)\s*(?P<unit>mm|mil|inch|in|um)?\s*$",
    re.IGNORECASE,
)


def parse_eagle_length_mm(raw: str | None, default_mm: float = 0.0) -> float:
    """Convert an EAGLE design-rule length string (e.g. ``'40mil'``) to mm.

    Supports ``mm``, ``mil`` (0.0254 mm), ``inch``/``in`` (25.4 mm), and
    ``um`` (0.001 mm). Bare numeric values are interpreted as millimeters.
    """
    if not raw:
        return default_mm
    match = _UNIT_VALUE_RE.match(raw)
    if not match:
        return default_mm
    val = float(match.group("num"))
    unit = (match.group("unit") or "mm").lower()
    if unit == "mm":
        return val
    if unit == "mil":
        return val * 0.0254
    if unit in ("inch", "in"):
        return val * 25.4
    if unit == "um":
        return val * 0.001
    return val


class EagleBoardParser:
    """Parses CadSoft EAGLE v6.6.0 XML ``.brd`` files into a ``BoardModel``.

    Args:
        courtyard_margin_mm: Uniform expansion added to fallback courtyards
            (packages that do not define explicit ``tKeepout``/``bKeepout``
            shapes). Default is ``0.25`` mm.
        default_edge_clearance_mm: Fallback copper-to-board-edge clearance if
            ``mdCopperDimension`` is missing from ``<designrules>``.
    """

    def __init__(
        self,
        courtyard_margin_mm: float = 0.25,
        default_edge_clearance_mm: float = 0.5,
    ) -> None:
        self.courtyard_margin_mm = courtyard_margin_mm
        self.default_edge_clearance_mm = default_edge_clearance_mm

    def parse(self, brd_path: str | Path) -> BoardModel:
        """Parse ``brd_path`` read-only and return a ``BoardModel``."""
        path = Path(brd_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Board file not found: {path}")

        tree = ET.parse(path)
        root = tree.getroot()
        if root.tag != "eagle":
            raise ValueError(
                f"Expected <eagle> root element in {path}, found <{root.tag}>"
            )
        eagle_version = root.attrib.get("version", "unknown")

        board_el = root.find("./drawing/board")
        if board_el is None:
            raise ValueError(f"No <drawing>/<board> section found in {path}")

        design_rules = self._parse_design_rules(board_el)
        outline, keepouts, holes = self._parse_plain(board_el)
        footprints = self._parse_libraries(board_el)
        components = self._parse_elements(board_el, footprints)
        nets = self._parse_signals(board_el)

        return BoardModel(
            source_path=path,
            eagle_version=eagle_version,
            outline=outline,
            design_rules=design_rules,
            components=components,
            nets=nets,
            keepouts=tuple(keepouts),
            holes=tuple(holes),
        )

    def _parse_design_rules(self, board_el: ET.Element) -> DesignRules:
        """Extract relevant placement clearances from ``<designrules>``."""
        dr_el = board_el.find("designrules")
        if dr_el is None:
            return DesignRules(edge_clearance_mm=self.default_edge_clearance_mm)

        name = dr_el.attrib.get("name", "default")
        edge_mm = self.default_edge_clearance_mm
        for param in dr_el.findall("param"):
            if param.attrib.get("name") == "mdCopperDimension":
                edge_mm = parse_eagle_length_mm(
                    param.attrib.get("value"), default_mm=self.default_edge_clearance_mm
                )
        return DesignRules(name=name, edge_clearance_mm=edge_mm)

    def _parse_plain(
        self, board_el: ET.Element
    ) -> tuple[BoardOutline, list[KeepoutRegion], list[BoardHole]]:
        """Extract layer 20 board outline, keepout/restrict regions, and holes."""
        plain_el = board_el.find("plain")
        dim_segments: list[tuple[Point2D, Point2D]] = []
        keepouts: list[KeepoutRegion] = []
        holes: list[BoardHole] = []

        if plain_el is not None:
            for child in plain_el:
                tag = child.tag
                layer = int(child.attrib.get("layer", "-1"))

                if tag == "wire" and layer == LAYER_DIMENSION:
                    p1 = Point2D(float(child.attrib["x1"]), float(child.attrib["y1"]))
                    p2 = Point2D(float(child.attrib["x2"]), float(child.attrib["y2"]))
                    dim_segments.append((p1, p2))

                elif tag == "hole":
                    holes.append(
                        BoardHole(
                            center=Point2D(
                                float(child.attrib["x"]), float(child.attrib["y"])
                            ),
                            drill_mm=float(child.attrib["drill"]),
                        )
                    )

                elif tag == "rectangle" and layer in (
                    LAYER_TKEEPOUT,
                    LAYER_BKEEPOUT,
                    LAYER_TRESTRICT,
                    LAYER_BRESTRICT,
                ):
                    x1 = float(child.attrib["x1"])
                    y1 = float(child.attrib["y1"])
                    x2 = float(child.attrib["x2"])
                    y2 = float(child.attrib["y2"])
                    rect = Rect2D(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
                    side: BoardSide = (
                        "top" if layer in (LAYER_TKEEPOUT, LAYER_TRESTRICT) else "bottom"
                    )
                    keepouts.append(KeepoutRegion(bounds=rect, side=side, layer=layer))

                elif tag == "polygon" and layer in (
                    LAYER_TKEEPOUT,
                    LAYER_BKEEPOUT,
                    LAYER_TRESTRICT,
                    LAYER_BRESTRICT,
                ):
                    verts = [
                        Point2D(float(v.attrib["x"]), float(v.attrib["y"]))
                        for v in child.findall("vertex")
                    ]
                    if verts:
                        side = (
                            "top"
                            if layer in (LAYER_TKEEPOUT, LAYER_TRESTRICT)
                            else "bottom"
                        )
                        keepouts.append(
                            KeepoutRegion(
                                bounds=Rect2D.from_points(verts),
                                side=side,
                                layer=layer,
                            )
                        )

        outline = self._build_outline(dim_segments)
        return outline, keepouts, holes

    def _build_outline(
        self, dim_segments: list[tuple[Point2D, Point2D]]
    ) -> BoardOutline:
        """Assemble a ``BoardOutline`` from layer 20 ``Dimension`` wire segments."""
        if not dim_segments:
            raise ValueError(
                "No layer 20 (Dimension) outline wires found in <board>/<plain>"
            )
        all_pts = [pt for seg in dim_segments for pt in seg]
        bounds = Rect2D.from_points(all_pts)

        # Detect whether all dimension segments are axis-aligned on the outer
        # bounding box (the common rectangular PCB fast path).
        eps = 1e-4
        is_rect = len(dim_segments) == 4 and all(
            (abs(p1.x - p2.x) < eps or abs(p1.y - p2.y) < eps)
            for p1, p2 in dim_segments
        )
        if is_rect:
            return BoardOutline(bounds=bounds, polygon=None, is_axis_aligned_rect=True)

        # Chain segments into an ordered polygon loop for non-rectangular boards.
        polygon = self._chain_segments_to_polygon(dim_segments)
        return BoardOutline(
            bounds=bounds,
            polygon=tuple(polygon) if polygon else None,
            is_axis_aligned_rect=False,
        )

    @staticmethod
    def _chain_segments_to_polygon(
        segments: list[tuple[Point2D, Point2D]], tol: float = 1e-3
    ) -> list[Point2D]:
        """Order connected boundary segments into a vertex list."""
        remaining = list(segments)
        start, current = remaining.pop(0)
        poly = [start, current]

        while remaining:
            found_idx: int | None = None
            next_pt: Point2D | None = None
            for idx, (a, b) in enumerate(remaining):
                if current.distance_to(a) <= tol:
                    found_idx = idx
                    next_pt = b
                    break
                if current.distance_to(b) <= tol:
                    found_idx = idx
                    next_pt = a
                    break
            if found_idx is None or next_pt is None:
                break
            remaining.pop(found_idx)
            if next_pt.distance_to(start) <= tol:
                break
            poly.append(next_pt)
            current = next_pt

        return poly

    def _parse_libraries(
        self, board_el: ET.Element
    ) -> dict[tuple[str, str], Footprint]:
        """Parse all ``<package>`` definitions from ``<libraries>``."""
        footprints: dict[tuple[str, str], Footprint] = {}
        libs_el = board_el.find("libraries")
        if libs_el is None:
            return footprints

        for lib_el in libs_el.findall("library"):
            lib_name = lib_el.attrib["name"]
            pkgs_el = lib_el.find("packages")
            if pkgs_el is None:
                continue
            for pkg_el in pkgs_el.findall("package"):
                fp = self._parse_package(lib_name, pkg_el)
                footprints[fp.key] = fp
        return footprints

    def _parse_package(self, lib_name: str, pkg_el: ET.Element) -> Footprint:
        """Build a ``Footprint`` with pins and package-local courtyard."""
        pkg_name = pkg_el.attrib["name"]
        pins: dict[str, Pin] = {}
        keepout_rects: list[Rect2D] = []
        fallback_rects: list[Rect2D] = []
        is_tht = False

        for child in pkg_el:
            tag = child.tag

            if tag == "pad":
                is_tht = True
                x = float(child.attrib["x"])
                y = float(child.attrib["y"])
                drill = float(child.attrib.get("drill", "0.8"))
                diameter = float(child.attrib.get("diameter", "0") or "0")
                # EAGLE auto-calculates pad diameter if omitted or 0 (~1.5x drill).
                radius = 0.5 * (diameter if diameter > 0 else max(drill * 1.5, drill + 0.4))
                pin_name = child.attrib["name"]
                pins[pin_name] = Pin(
                    name=pin_name, position=Point2D(x, y), is_through_hole=True
                )
                fallback_rects.append(
                    Rect2D(x - radius, y - radius, x + radius, y + radius)
                )

            elif tag == "smd":
                x = float(child.attrib["x"])
                y = float(child.attrib["y"])
                dx = float(child.attrib["dx"])
                dy = float(child.attrib["dy"])
                smd_rot = child.attrib.get("rot", "R0")
                pin_name = child.attrib["name"]
                pins[pin_name] = Pin(
                    name=pin_name, position=Point2D(x, y), is_through_hole=False
                )
                local_smd = Rect2D(-0.5 * dx, -0.5 * dy, 0.5 * dx, 0.5 * dy)
                smd_tf = ElementTransform.from_eagle_rot(x, y, smd_rot)
                fallback_rects.append(smd_tf.apply_rect(local_smd))

            elif tag == "hole":
                is_tht = True
                x = float(child.attrib["x"])
                y = float(child.attrib["y"])
                r = 0.5 * float(child.attrib["drill"])
                fallback_rects.append(Rect2D(x - r, y - r, x + r, y + r))

            elif tag == "wire":
                layer = int(child.attrib.get("layer", "-1"))
                if layer in (LAYER_TKEEPOUT, LAYER_BKEEPOUT, LAYER_TPLACE, LAYER_BPLACE):
                    x1 = float(child.attrib["x1"])
                    y1 = float(child.attrib["y1"])
                    x2 = float(child.attrib["x2"])
                    y2 = float(child.attrib["y2"])
                    half_w = 0.5 * float(child.attrib.get("width", "0"))
                    rect = Rect2D(
                        min(x1, x2) - half_w,
                        min(y1, y2) - half_w,
                        max(x1, x2) + half_w,
                        max(y1, y2) + half_w,
                    )
                    if layer in (LAYER_TKEEPOUT, LAYER_BKEEPOUT):
                        keepout_rects.append(rect)
                    else:
                        fallback_rects.append(rect)

            elif tag == "rectangle":
                layer = int(child.attrib.get("layer", "-1"))
                if layer in (LAYER_TKEEPOUT, LAYER_BKEEPOUT, LAYER_TPLACE, LAYER_BPLACE):
                    x1 = float(child.attrib["x1"])
                    y1 = float(child.attrib["y1"])
                    x2 = float(child.attrib["x2"])
                    y2 = float(child.attrib["y2"])
                    rect = Rect2D(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
                    if layer in (LAYER_TKEEPOUT, LAYER_BKEEPOUT):
                        keepout_rects.append(rect)
                    else:
                        fallback_rects.append(rect)

            elif tag == "circle":
                layer = int(child.attrib.get("layer", "-1"))
                if layer in (LAYER_TKEEPOUT, LAYER_BKEEPOUT, LAYER_TPLACE, LAYER_BPLACE):
                    cx = float(child.attrib["x"])
                    cy = float(child.attrib["y"])
                    r = float(child.attrib["radius"]) + 0.5 * float(
                        child.attrib.get("width", "0")
                    )
                    rect = Rect2D(cx - r, cy - r, cx + r, cy + r)
                    if layer in (LAYER_TKEEPOUT, LAYER_BKEEPOUT):
                        keepout_rects.append(rect)
                    else:
                        fallback_rects.append(rect)

        if keepout_rects:
            local_courtyard = Rect2D.union(keepout_rects)
            courtyard_source = "keepout"
        elif fallback_rects:
            local_courtyard = Rect2D.union(fallback_rects).expanded(
                self.courtyard_margin_mm
            )
            courtyard_source = "fallback"
        else:
            # Degenerate empty package (e.g., fiducial or mechanical mark).
            m = max(self.courtyard_margin_mm, 0.25)
            local_courtyard = Rect2D(-m, -m, m, m)
            courtyard_source = "fallback"

        return Footprint(
            library=lib_name,
            name=pkg_name,
            pins=pins,
            local_courtyard=local_courtyard,
            is_through_hole=is_tht,
            courtyard_source=courtyard_source,
        )

    def _parse_elements(
        self,
        board_el: ET.Element,
        footprints: dict[tuple[str, str], Footprint],
    ) -> dict[str, Component]:
        """Parse all ``<element>`` instances from ``<elements>``."""
        components: dict[str, Component] = {}
        elements_el = board_el.find("elements")
        if elements_el is None:
            return components

        for el in elements_el.findall("element"):
            name = el.attrib["name"]
            lib = el.attrib["library"]
            pkg = el.attrib["package"]
            value = el.attrib.get("value", "")
            x = float(el.attrib["x"])
            y = float(el.attrib["y"])
            rot = el.attrib.get("rot")
            is_locked = el.attrib.get("locked", "no").lower() == "yes"

            fp = footprints.get((lib, pkg))
            if fp is None:
                raise KeyError(
                    f"Element {name!r} references missing package ({lib!r}, {pkg!r})"
                )
            pose = ElementTransform.from_eagle_rot(x=x, y=y, rot=rot)
            components[name] = Component(
                name=name,
                value=value,
                footprint=fp,
                initial_pose=pose,
                is_locked=is_locked,
            )
        return components

    def _parse_signals(self, board_el: ET.Element) -> dict[str, Net]:
        """Parse all ``<signal>`` nets, detecting routed copper and pours."""
        nets: dict[str, Net] = {}
        signals_el = board_el.find("signals")
        if signals_el is None:
            return nets

        for sig_el in signals_el.findall("signal"):
            name = sig_el.attrib["name"]
            contacts: list[ContactRef] = []
            has_routed = False
            has_pour = False

            for child in sig_el:
                if child.tag == "contactref":
                    contacts.append(
                        ContactRef(
                            component_name=child.attrib["element"],
                            pin_name=child.attrib["pad"],
                        )
                    )
                elif child.tag in ("wire", "via"):
                    # Ignore unrouted airwire layer (19) if ever present as <wire>.
                    layer = int(child.attrib.get("layer", "1"))
                    if child.tag == "via" or layer != 19:
                        has_routed = True
                elif child.tag == "polygon":
                    has_pour = True

            nets[name] = Net(
                name=name,
                contacts=tuple(contacts),
                has_routed_copper=has_routed,
                has_copper_pour=has_pour,
            )
        return nets
