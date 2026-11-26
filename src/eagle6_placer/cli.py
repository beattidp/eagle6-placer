"""Command-line interface for ``eagle6-placer``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from eagle6_placer import __version__
from eagle6_placer.cost import CostConfig
from eagle6_placer.emitter import EagleScriptEmitter
from eagle6_placer.optimizer import (
    LocalPolishOptimizer,
    PolishConfig,
    RoutedCopperError,
)
from eagle6_placer.parser import EagleBoardParser


def _parse_proximity_groups(raw_groups: list[str] | None) -> tuple[tuple[str, ...], ...]:
    """Parse ``--proximity-group C1,U1`` arguments into tuples of part names."""
    if not raw_groups:
        return ()
    groups: list[tuple[str, ...]] = []
    for raw in raw_groups:
        parts = tuple(p.strip() for p in raw.split(",") if p.strip())
        if len(parts) >= 2:
            groups.append(parts)
    return tuple(groups)


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="eagle6-placer",
        description=(
            "Optimize unlocked component placement on CadSoft EAGLE v6.6.0 "
            ".brd files and emit human-reviewable .scr scripts."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    polish = subparsers.add_parser(
        "polish",
        help="Run local polish Simulated Annealing (keep-side default) on a .brd file.",
    )
    polish.add_argument("board", type=Path, help="Path to input EAGLE v6.6.0 .brd file")
    polish.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for .scr and .json files (default: <board_dir>/placer)",
    )
    polish.add_argument(
        "--grid-mm",
        type=float,
        default=0.5,
        help="Placement snap grid in mm (default: 0.5)",
    )
    polish.add_argument(
        "--courtyard-margin-mm",
        type=float,
        default=0.25,
        help="Fallback courtyard margin in mm (default: 0.25)",
    )
    polish.add_argument(
        "--edge-clearance-mm",
        type=float,
        default=None,
        help="Override board-edge clearance in mm (default: from <designrules>)",
    )
    polish.add_argument(
        "--steps",
        type=int,
        default=4000,
        help="Number of Simulated Annealing iterations (default: 4000)",
    )
    polish.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic PRNG seed (default: 42)",
    )
    polish.add_argument(
        "--displacement-weight",
        type=float,
        default=0.1,
        help="Weight on displacement from initial positions (default: 0.1)",
    )
    polish.add_argument(
        "--crossing-weight",
        type=float,
        default=5.0,
        help="Weight per airwire crossing between signal nets (default: 5.0)",
    )
    polish.add_argument(
        "--pour-net-weight",
        type=float,
        default=0.05,
        help="Wirelength weight for global/pour nets such as GND/VCC (default: 0.05)",
    )
    polish.add_argument(
        "--proximity-group",
        action="append",
        default=None,
        help="Comma-separated component names to keep close (repeatable, e.g. C1,U1)",
    )
    polish.add_argument(
        "--allow-routed",
        action="store_true",
        help="Allow optimizing unlocked parts attached to already-routed copper",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning POSIX exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "polish":
        try:
            board_parser = EagleBoardParser(
                courtyard_margin_mm=args.courtyard_margin_mm
            )
            board = board_parser.parse(args.board)

            cost_cfg = CostConfig(
                crossing_weight=args.crossing_weight,
                displacement_weight=args.displacement_weight,
                pour_net_weight=args.pour_net_weight,
                proximity_groups=_parse_proximity_groups(args.proximity_group),
            )
            polish_cfg = PolishConfig(
                steps=args.steps,
                grid_mm=args.grid_mm,
                seed=args.seed,
                allow_routed=args.allow_routed,
                allow_mirror=False,
                edge_clearance_mm=args.edge_clearance_mm,
                cost_config=cost_cfg,
            )

            optimizer = LocalPolishOptimizer(board, polish_cfg)
            result = optimizer.optimize()

            emitter = EagleScriptEmitter()
            script_path, report_path = emitter.write_outputs(
                board, result, output_dir=args.output_dir
            )
        except (FileNotFoundError, ValueError, KeyError, RoutedCopperError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

        init_c = result.initial_cost
        best_c = result.best_cost
        deltas = emitter.compute_deltas(board, result)
        print(f"Board:      {board.source_path.name} (EAGLE {board.eagle_version})")
        print(
            f"Components: {len(board.components)} total "
            f"({len(board.locked_components)} locked, "
            f"{len(board.unlocked_components)} unlocked, "
            f"{len(deltas)} modified)"
        )
        print(
            f"Weighted MST: {init_c.weighted_mst_wirelength_mm:.2f} mm -> "
            f"{best_c.weighted_mst_wirelength_mm:.2f} mm"
        )
        print(
            f"Raw MST:      {init_c.raw_mst_wirelength_mm:.2f} mm -> "
            f"{best_c.raw_mst_wirelength_mm:.2f} mm"
        )
        print(
            f"Crossings:    {init_c.airwire_crossings} -> {best_c.airwire_crossings}"
        )
        print(f"Total cost:   {init_c.total_cost:.2f} -> {best_c.total_cost:.2f}")
        print(f"Audit:        {'PASS (0 violations)' if not result.final_violations else f'FAIL ({len(result.final_violations)} violations)'}")
        print(f"Script:       {script_path}")
        print(f"Report:       {report_path}")
        return 0 if not result.final_violations else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
