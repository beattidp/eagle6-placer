"""Before/After SVG & PNG placement preview renderer for CadSoft EAGLE v6 boards.

Renders the full board outline (fitted cleanly with padding at configurable
pixel density), mechanical holes, keepouts, component courtyards, transformed
``tPlace``/``bPlace`` silkscreen outlines (enabled by default; toggleable via
``show_place=False`` / ``--hide-place``), copper pads, and non-pour signal
MST airwires.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from eagle6_placer.cost import CostConfig, RoutabilityEvaluator, compute_euclidean_mst
from eagle6_placer.models import BoardModel, PlacementState
from eagle6_placer.optimizer import OptimizationResult


@dataclass(frozen=True)
class PreviewOptions:
    """Visual configuration for ``PlacementPreviewRenderer``."""

    show_place: bool = True
    pixels_per_mm: float = 18.0
    margin_px: int = 44
    header_px: int = 62
    footer_px: int = 30
    gap_px: int = 24


class PlacementPreviewRenderer:
    """Generates side-by-side Before/After SVG (and PNG when available) previews."""

    def __init__(
        self,
        board: BoardModel,
        cost_config: CostConfig | None = None,
        options: PreviewOptions | None = None,
    ) -> None:
        self.board = board
        self.evaluator = RoutabilityEvaluator(board, cost_config or CostConfig())
        self.options = options or PreviewOptions()

    def _render_panel(
        self,
        state: PlacementState,
        title: str,
        subtitle: str,
        x_offset: float,
        panel_w: float,
        panel_h: float,
    ) -> list[str]:
        """Render a single Before or After board panel as SVG elements."""
        opt = self.options
        scale = opt.pixels_per_mm
        bounds = self.board.outline.bounds
        bw = bounds.width
        bh = bounds.height

        def tx(x: float) -> float:
            return x_offset + opt.margin_px + (x - bounds.min_x) * scale

        def ty(y: float) -> float:
            return opt.header_px + (bounds.max_y - y) * scale

        out: list[str] = [
            f'<rect x="{x_offset:.1f}" y="0" width="{panel_w:.1f}" height="{panel_h:.1f}" fill="#0d0f12"/>',
            (
                f'<text x="{x_offset + opt.margin_px:.1f}" y="26" fill="#f0f4f8" '
                f'font-family="monospace" font-size="17" font-weight="bold">{escape(title)}</text>'
            ),
            (
                f'<text x="{x_offset + opt.margin_px:.1f}" y="46" fill="#9fb3c8" '
                f'font-family="monospace" font-size="12.5">{escape(subtitle)}</text>'
            ),
        ]

        # Board outline (layer 20 Dimension)
        if self.board.outline.polygon and not self.board.outline.is_axis_aligned_rect:
            pts_str = " ".join(
                f"{tx(p.x):.1f},{ty(p.y):.1f}" for p in self.board.outline.polygon
            )
            out.append(
                f'<polygon points="{pts_str}" fill="#14181f" stroke="#e2e8f0" stroke-width="2.0"/>'
            )
        else:
            out.append(
                f'<rect x="{tx(bounds.min_x):.1f}" y="{ty(bounds.max_y):.1f}" '
                f'width="{bw * scale:.1f}" height="{bh * scale:.1f}" '
                f'fill="#14181f" stroke="#e2e8f0" stroke-width="2.0"/>'
            )

        # Keepout regions
        for ko in self.board.keepouts:
            k_stroke = "#f0b429" if ko.side == "top" else "#4098d7"
            out.append(
                f'<rect x="{tx(ko.bounds.min_x):.1f}" y="{ty(ko.bounds.max_y):.1f}" '
                f'width="{ko.bounds.width * scale:.1f}" height="{ko.bounds.height * scale:.1f}" '
                f'fill="{k_stroke}" fill-opacity="0.14" stroke="{k_stroke}" '
                f'stroke-dasharray="4 3" stroke-width="1.2"/>'
            )

        # Mechanical holes
        for hole in self.board.holes:
            out.append(
                f'<circle cx="{tx(hole.center.x):.1f}" cy="{ty(hole.center.y):.1f}" '
                f'r="{hole.radius_mm * scale:.1f}" fill="#0d0f12" stroke="#cbd5e1" stroke-width="1.4"/>'
            )

        # Components ordered: locked -> bottom unlocked -> top unlocked
        ordered = sorted(
            self.board.components.values(),
            key=lambda c: (
                0 if c.is_locked else (1 if state.poses[c.name].mirrored else 2),
                c.name,
            ),
        )
        for comp in ordered:
            pose = state.poses[comp.name]
            rect = comp.courtyard_at(pose)
            if comp.is_locked:
                fill, stroke, text_col = "#1e3a5f", "#64748b", "#cbd5e1"
            elif pose.mirrored:
                fill, stroke, text_col = "#102a43", "#3b82f6", "#93c5fd"
            else:
                fill, stroke, text_col = "#4a151b", "#ef4444", "#fecaca"

            # Courtyard box (subtle when tPlace/bPlace is shown so silkscreen pops)
            fill_opacity = "0.35" if opt.show_place else "0.70"
            stroke_w = "1.0" if opt.show_place else "1.4"
            out.append(
                f'<rect x="{tx(rect.min_x):.1f}" y="{ty(rect.max_y):.1f}" '
                f'width="{rect.width * scale:.1f}" height="{rect.height * scale:.1f}" '
                f'fill="{fill}" fill-opacity="{fill_opacity}" stroke="{stroke}" '
                f'stroke-width="{stroke_w}"/>'
            )

            # Copper pads / SMDs
            for pin in comp.footprint.pins.values():
                pt = pose.apply_point(pin.position)
                if pin.is_through_hole:
                    pcol, pr = "#22c55e", 3.0
                elif pose.mirrored:
                    pcol, pr = "#60a5fa", 2.4
                else:
                    pcol, pr = "#f87171", 2.4
                out.append(
                    f'<circle cx="{tx(pt.x):.1f}" cy="{ty(pt.y):.1f}" r="{pr:.1f}" fill="{pcol}"/>'
                )

            # Active tPlace / bPlace silkscreen geometry (default on)
            if opt.show_place:
                silk_col = "#93c5fd" if pose.mirrored else "#e2e8f0"
                for line in comp.footprint.silk_lines:
                    bp1 = pose.apply_point(line.p1)
                    bp2 = pose.apply_point(line.p2)
                    sw = max(1.1, min(2.6, line.width_mm * scale * 0.45))
                    out.append(
                        f'<line x1="{tx(bp1.x):.1f}" y1="{ty(bp1.y):.1f}" '
                        f'x2="{tx(bp2.x):.1f}" y2="{ty(bp2.y):.1f}" '
                        f'stroke="{silk_col}" stroke-width="{sw:.2f}" stroke-linecap="round" '
                        f'stroke-opacity="0.92"/>'
                    )
                for srect in comp.footprint.silk_rects:
                    brect = pose.apply_rect(srect.rect)
                    out.append(
                        f'<rect x="{tx(brect.min_x):.1f}" y="{ty(brect.max_y):.1f}" '
                        f'width="{brect.width * scale:.1f}" height="{brect.height * scale:.1f}" '
                        f'fill="none" stroke="{silk_col}" stroke-width="1.2" stroke-opacity="0.9"/>'
                    )
                for circ in comp.footprint.silk_circles:
                    bc = pose.apply_point(circ.center)
                    out.append(
                        f'<circle cx="{tx(bc.x):.1f}" cy="{ty(bc.y):.1f}" '
                        f'r="{circ.radius_mm * scale:.1f}" fill="none" '
                        f'stroke="{silk_col}" stroke-width="1.2" stroke-opacity="0.9"/>'
                    )

            # Component designator
            out.append(
                f'<text x="{tx(rect.center.x):.1f}" y="{ty(rect.center.y) + 3.5:.1f}" '
                f'text-anchor="middle" fill="{text_col}" font-family="monospace" '
                f'font-size="10.5" font-weight="bold">{escape(comp.name)}</text>'
            )

        # Signal MST airwires (non-pour nets)
        for net in self.board.nets.values():
            if len(net.contacts) < 2 or self.evaluator.is_pour_net(net.name):
                continue
            pts = [
                self.board.components[ref.component_name].pin_position(
                    ref.pin_name, state.poses[ref.component_name]
                )
                for ref in net.contacts
                if ref.component_name in self.board.components
                and ref.pin_name
                in self.board.components[ref.component_name].footprint.pins
            ]
            _, edges = compute_euclidean_mst(pts)
            for seg in edges:
                out.append(
                    f'<line x1="{tx(seg.p1.x):.1f}" y1="{ty(seg.p1.y):.1f}" '
                    f'x2="{tx(seg.p2.x):.1f}" y2="{ty(seg.p2.y):.1f}" '
                    f'stroke="#facc15" stroke-width="1.25" stroke-opacity="0.88"/>'
                )

        return out

    def render_comparison_svg(self, result: OptimizationResult) -> str:
        """Render side-by-side Before and After boards as a single SVG string."""
        opt = self.options
        bounds = self.board.outline.bounds
        panel_w = bounds.width * opt.pixels_per_mm + 2 * opt.margin_px
        panel_h = bounds.height * opt.pixels_per_mm + opt.header_px + opt.footer_px
        total_w = int(round(2 * panel_w + opt.gap_px))
        total_h = int(round(panel_h))

        init_c = result.initial_cost
        best_c = result.best_cost
        cross_delta = (
            f" ({(best_c.airwire_crossings - init_c.airwire_crossings) / init_c.airwire_crossings * 100:+.1f}%)"
            if init_c.airwire_crossings > 0
            else ""
        )

        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{total_h}" '
            f'viewBox="0 0 {total_w} {total_h}">',
            f'<rect width="{total_w}" height="{total_h}" fill="#08090c"/>',
        ]
        lines.extend(
            self._render_panel(
                result.initial_state,
                title=f"BEFORE: {self.board.source_path.name}",
                subtitle=(
                    f"Weighted MST: {init_c.weighted_mst_wirelength_mm:.1f} mm | "
                    f"Raw MST: {init_c.raw_mst_wirelength_mm:.1f} mm | "
                    f"Crossings: {init_c.airwire_crossings} | "
                    f"Overlaps: {init_c.overlap_violations}"
                ),
                x_offset=0.0,
                panel_w=panel_w,
                panel_h=panel_h,
            )
        )
        lines.extend(
            self._render_panel(
                result.best_state,
                title=f"AFTER: {self.board.source_path.name} (seed {result.seed})",
                subtitle=(
                    f"Weighted MST: {best_c.weighted_mst_wirelength_mm:.1f} mm | "
                    f"Raw MST: {best_c.raw_mst_wirelength_mm:.1f} mm | "
                    f"Crossings: {best_c.airwire_crossings}{cross_delta} | "
                    f"Overlaps: {best_c.overlap_violations}"
                ),
                x_offset=panel_w + opt.gap_px,
                panel_w=panel_w,
                panel_h=panel_h,
            )
        )

        place_note = " | [White/LtBlue]=tPlace/bPlace" if opt.show_place else ""
        lines.append(
            f'<text x="{opt.margin_px}" y="{total_h - 10}" fill="#9fb3c8" '
            f'font-family="monospace" font-size="11">'
            f"Legend: [Slate]=Locked | [Red]=Unlocked Top | [Blue]=Unlocked Bottom | "
            f"[Green]=THT Pad | [Yellow]=Signal MST Airwires{place_note}"
            "</text>"
        )
        lines.append("</svg>")
        return "\n".join(lines)

    def write_preview(
        self, result: OptimizationResult, output_dir: str | Path
    ) -> tuple[Path, Path | None]:
        """Write ``<stem>_preview.svg`` and, if ImageMagick is installed, ``.png``."""
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = self.board.source_path.stem
        svg_path = out_dir / f"{stem}_preview.svg"
        png_path = out_dir / f"{stem}_preview.png"

        svg_path.write_text(self.render_comparison_svg(result), encoding="utf-8")

        converter = shutil.which("convert") or shutil.which("magick")
        if converter:
            try:
                subprocess.run(
                    [converter, str(svg_path), str(png_path)],
                    check=True,
                    capture_output=True,
                )
                return svg_path, png_path
            except subprocess.CalledProcessError:
                return svg_path, None

        return svg_path, None
