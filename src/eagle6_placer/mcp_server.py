"""Decoupled Model Context Protocol (MCP) stdio server for ``eagle6-placer``.

Exposes read-only board placement auditing, local polish optimization, and
coarse-to-fine placement as MCP tools while preserving all core safety
invariants (never mutates ``.brd``/``.sch`` XML; emits ``.scr`` scripts for
staged dry-run via ``eagle6-mcp`` and EAGLE GUI execution with full Undo).

Supports both ``mcp>=2.0`` (``MCPServer``) and ``mcp 1.x`` (``FastMCP``).
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from eagle6_placer import __version__
from eagle6_placer.candidates import MultiSeedRunner, PlacementMode
from eagle6_placer.constraints import ConstraintChecker
from eagle6_placer.cost import CostConfig, RoutabilityEvaluator
from eagle6_placer.emitter import EagleScriptEmitter
from eagle6_placer.optimizer import PolishConfig, RoutedCopperError
from eagle6_placer.parser import EagleBoardParser
from eagle6_placer.preview import PlacementPreviewRenderer, PreviewOptions
from eagle6_placer.selection import resolve_mirrorable_components

SERVER_INSTRUCTIONS = (
    "eagle6-placer optimizes unlocked component placement on CadSoft EAGLE "
    "v6.6.0 .brd files read-only and emits human-reviewable .scr scripts. "
    "Never mutate .brd/.sch XML directly; dry-run returned script_content "
    "via eagle6-mcp's validate_edit_script and run_drc before GUI execution."
)


def _normalize_proximity_groups(
    proximity_groups: list[list[str]] | list[str] | None,
) -> tuple[tuple[str, ...], ...]:
    """Normalize MCP proximity_groups input (list of lists or comma strings)."""
    if not proximity_groups:
        return ()
    groups: list[tuple[str, ...]] = []
    for item in proximity_groups:
        if isinstance(item, str):
            parts = tuple(p.strip() for p in item.split(",") if p.strip())
        else:
            parts = tuple(str(p).strip() for p in item if str(p).strip())
        if len(parts) >= 2:
            groups.append(parts)
    return tuple(groups)


def audit_placement_board(
    brd_path: str,
    courtyard_margin_mm: float = 0.25,
    edge_clearance_mm: float | None = None,
    ignore_pour_copper: bool = True,
) -> dict[str, Any]:
    """Perform a read-only placement audit on a CadSoft EAGLE v6.6.0 ``.brd``."""
    board = EagleBoardParser(courtyard_margin_mm=courtyard_margin_mm).parse(brd_path)
    checker = ConstraintChecker(board, edge_clearance_mm=edge_clearance_mm)
    init_state = board.initial_state()
    violations = checker.audit_state(init_state)

    evaluator = RoutabilityEvaluator(board, CostConfig())
    init_cost = evaluator.evaluate(init_state, overlap_violations=len(violations))
    routed_unlocked = board.routed_unlocked_components(
        ignore_pour_nets=ignore_pour_copper
    )

    return {
        "tool": "eagle6-placer",
        "version": __version__,
        "source_board": str(board.source_path),
        "eagle_version": board.eagle_version,
        "outline_mm": {
            "min_x": board.outline.bounds.min_x,
            "min_y": board.outline.bounds.min_y,
            "max_x": board.outline.bounds.max_x,
            "max_y": board.outline.bounds.max_y,
            "width": board.outline.bounds.width,
            "height": board.outline.bounds.height,
            "edge_clearance_mm": checker.edge_clearance_mm,
        },
        "components": {
            "total": len(board.components),
            "locked_count": len(board.locked_components),
            "unlocked_count": len(board.unlocked_components),
            "locked_names": sorted(c.name for c in board.locked_components),
            "unlocked_names": sorted(c.name for c in board.unlocked_components),
        },
        "routed_copper_guard": {
            "ignore_pour_copper": ignore_pour_copper,
            "blocked_unlocked_components": routed_unlocked,
            "ready_without_allow_routed": len(routed_unlocked) == 0,
        },
        "initial_metrics": asdict(init_cost),
        "initial_audit": {
            "passed": len(violations) == 0,
            "violation_count": len(violations),
            "violations": [asdict(v) for v in violations],
        },
    }


def optimize_board_placement(
    brd_path: str,
    *,
    mode: PlacementMode = "polish",
    output_dir: str | None = None,
    grid_mm: float = 0.5,
    courtyard_margin_mm: float = 0.25,
    edge_clearance_mm: float | None = None,
    steps: int = 4000,
    seed: int = 42,
    displacement_weight: float = 0.1,
    crossing_weight: float = 5.0,
    congestion_weight: float = 0.5,
    pour_net_weight: float = 0.05,
    overlap_penalty: float = 250.0,
    allow_mirror: bool = False,
    allow_mirror_specs: list[str] | None = None,
    restrict_mirror_specs: list[str] | None = None,
    proximity_groups: list[list[str]] | list[str] | None = None,
    candidates: int = 1,
    keep_all_candidates: bool = False,
    allow_routed: bool = False,
    strict_routed: bool = False,
    preview: bool = True,
    hide_place: bool = False,
) -> dict[str, Any]:
    """Run ``polish`` or ``place`` optimization and return structured outputs."""
    board = EagleBoardParser(courtyard_margin_mm=courtyard_margin_mm).parse(brd_path)
    cost_cfg = CostConfig(
        crossing_weight=crossing_weight,
        congestion_weight=congestion_weight,
        displacement_weight=displacement_weight,
        pour_net_weight=pour_net_weight,
        overlap_penalty_weight=overlap_penalty,
        proximity_groups=_normalize_proximity_groups(proximity_groups),
    )

    mirror_enabled = allow_mirror or bool(allow_mirror_specs)
    mirrorable_names = resolve_mirrorable_components(
        board=board,
        allow_mirror_enabled=mirror_enabled,
        allow_specs=allow_mirror_specs,
        restrict_specs=restrict_mirror_specs,
    )

    polish_cfg = PolishConfig(
        steps=steps,
        grid_mm=grid_mm,
        seed=seed,
        allow_routed=allow_routed,
        ignore_pour_copper=not strict_routed,
        allow_mirror=mirror_enabled,
        mirrorable_names=mirrorable_names,
        edge_clearance_mm=edge_clearance_mm,
        cost_config=cost_cfg,
    )

    runner = MultiSeedRunner(board, polish_cfg, mode=mode)
    multi = runner.run(
        num_candidates=candidates,
        output_dir=output_dir,
        keep_all_candidates=keep_all_candidates,
    )
    result = multi.best_result

    emitter = EagleScriptEmitter()
    script_path, report_path = emitter.write_outputs(
        board, result, output_dir=output_dir
    )
    script_content = script_path.read_text(encoding="utf-8")

    preview_svg: Path | None = None
    preview_png: Path | None = None
    if preview:
        renderer = PlacementPreviewRenderer(
            board,
            cost_config=cost_cfg,
            options=PreviewOptions(show_place=not hide_place),
        )
        preview_svg, preview_png = renderer.write_preview(
            result, output_dir=script_path.parent
        )

    report = emitter.build_report(board, result, script_path=script_path)
    report["mode"] = mode
    report["report_path"] = str(report_path)
    report["manifest_path"] = (
        str(multi.manifest_path) if multi.manifest_path is not None else None
    )
    report["candidates"] = [asdict(r) for r in multi.records]
    report["preview_svg_path"] = str(preview_svg) if preview_svg is not None else None
    report["preview_png_path"] = str(preview_png) if preview_png is not None else None
    report["script_content"] = script_content
    return report


def create_mcp_server() -> Any:
    """Create and configure the ``eagle6-placer`` MCP server instance."""
    try:
        from mcp.server.mcpserver import MCPServer as ServerClass
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP as ServerClass  # type: ignore[no-redef]
        except ImportError as exc:
            raise ImportError(
                "The optional 'mcp' package is required to run eagle6-placer-mcp. "
                "Install it with: pip install 'eagle6-placer[mcp]'"
            ) from exc

    server = ServerClass("eagle6-placer", instructions=SERVER_INSTRUCTIONS)

    @server.tool()
    def audit_placement(
        brd_path: str,
        courtyard_margin_mm: float = 0.25,
        edge_clearance_mm: float | None = None,
        ignore_pour_copper: bool = True,
    ) -> dict[str, Any]:
        """Read-only placement audit of a CadSoft EAGLE v6.6.0 .brd file.

        Returns board dimensions, locked/unlocked part lists, routed-copper
        guard status, initial MST wirelength, airwire crossings, congestion,
        and any pre-existing courtyard/hole/keepout violations.
        """
        return audit_placement_board(
            brd_path=brd_path,
            courtyard_margin_mm=courtyard_margin_mm,
            edge_clearance_mm=edge_clearance_mm,
            ignore_pour_copper=ignore_pour_copper,
        )

    @server.tool()
    def polish_board(
        brd_path: str,
        output_dir: str | None = None,
        grid_mm: float = 0.5,
        courtyard_margin_mm: float = 0.25,
        edge_clearance_mm: float | None = None,
        steps: int = 4000,
        seed: int = 42,
        displacement_weight: float = 0.1,
        crossing_weight: float = 5.0,
        congestion_weight: float = 0.5,
        pour_net_weight: float = 0.05,
        overlap_penalty: float = 250.0,
        allow_mirror: bool = False,
        allow_mirror_specs: list[str] | None = None,
        restrict_mirror_specs: list[str] | None = None,
        proximity_groups: list[list[str]] | None = None,
        candidates: int = 1,
        keep_all_candidates: bool = False,
        allow_routed: bool = False,
        strict_routed: bool = False,
        preview: bool = True,
        hide_place: bool = False,
    ) -> dict[str, Any]:
        """Run local polish Simulated Annealing on an already-placed .brd file.

        Never mutates the .brd file. Writes human-reviewable .scr, .json,
        optional candidates_manifest.json, and Before/After preview images,
        and returns script_content ready for eagle6-mcp's validate_edit_script.
        """
        return optimize_board_placement(
            brd_path=brd_path,
            mode="polish",
            output_dir=output_dir,
            grid_mm=grid_mm,
            courtyard_margin_mm=courtyard_margin_mm,
            edge_clearance_mm=edge_clearance_mm,
            steps=steps,
            seed=seed,
            displacement_weight=displacement_weight,
            crossing_weight=crossing_weight,
            congestion_weight=congestion_weight,
            pour_net_weight=pour_net_weight,
            overlap_penalty=overlap_penalty,
            allow_mirror=allow_mirror,
            allow_mirror_specs=allow_mirror_specs,
            restrict_mirror_specs=restrict_mirror_specs,
            proximity_groups=proximity_groups,
            candidates=candidates,
            keep_all_candidates=keep_all_candidates,
            allow_routed=allow_routed,
            strict_routed=strict_routed,
            preview=preview,
            hide_place=hide_place,
        )

    @server.tool()
    def place_board(
        brd_path: str,
        output_dir: str | None = None,
        grid_mm: float = 0.5,
        courtyard_margin_mm: float = 0.25,
        edge_clearance_mm: float | None = None,
        steps: int = 5000,
        seed: int = 42,
        displacement_weight: float = 0.0,
        crossing_weight: float = 5.0,
        congestion_weight: float = 0.5,
        pour_net_weight: float = 0.05,
        overlap_penalty: float = 250.0,
        allow_mirror: bool = False,
        allow_mirror_specs: list[str] | None = None,
        restrict_mirror_specs: list[str] | None = None,
        proximity_groups: list[list[str]] | None = None,
        candidates: int = 1,
        keep_all_candidates: bool = False,
        allow_routed: bool = False,
        strict_routed: bool = False,
        preview: bool = True,
        hide_place: bool = False,
    ) -> dict[str, Any]:
        """Run coarse-to-fine placement (force-directed + legalization + SA).

        Designed for unplaced or scattered .brd files where unlocked components
        start off-board around locked anchors. Emits .scr, .json, optional
        candidates_manifest.json, and Before/After preview without mutating .brd.
        """
        return optimize_board_placement(
            brd_path=brd_path,
            mode="place",
            output_dir=output_dir,
            grid_mm=grid_mm,
            courtyard_margin_mm=courtyard_margin_mm,
            edge_clearance_mm=edge_clearance_mm,
            steps=steps,
            seed=seed,
            displacement_weight=displacement_weight,
            crossing_weight=crossing_weight,
            congestion_weight=congestion_weight,
            pour_net_weight=pour_net_weight,
            overlap_penalty=overlap_penalty,
            allow_mirror=allow_mirror,
            allow_mirror_specs=allow_mirror_specs,
            restrict_mirror_specs=restrict_mirror_specs,
            proximity_groups=proximity_groups,
            candidates=candidates,
            keep_all_candidates=keep_all_candidates,
            allow_routed=allow_routed,
            strict_routed=strict_routed,
            preview=preview,
            hide_place=hide_place,
        )

    return server


def main() -> None:
    """Console entry point launching ``eagle6-placer-mcp`` over stdio."""
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
