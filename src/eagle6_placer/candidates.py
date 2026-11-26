"""Multi-seed candidate exploration and decoupled manifest generation.

Runs ``K`` deterministic optimization seeds, ranks candidates by
``(constraint_violations, total_cost, airwire_crossings, weighted_mst)``,
and emits ``candidates_manifest.json`` so decoupled sibling tools
(``eagle6-mcp`` + ``eagle6-freerouting``) can optionally evaluate top-K
placement scripts by real autorouting outcomes with zero code coupling.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

from eagle6_placer import __version__
from eagle6_placer.coarse import CoarseConfig, CoarsePlacer
from eagle6_placer.emitter import EagleScriptEmitter
from eagle6_placer.models import BoardModel
from eagle6_placer.optimizer import (
    LocalPolishOptimizer,
    OptimizationResult,
    PolishConfig,
)

PlacementMode = Literal["polish", "place"]


@dataclass(frozen=True)
class CandidateRecord:
    """Summary of one candidate placement run for manifest export."""

    rank: int
    seed: int
    mode: PlacementMode
    passed_audit: bool
    violation_count: int
    total_cost: float
    weighted_mst_wirelength_mm: float
    raw_mst_wirelength_mm: float
    airwire_crossings: int
    congestion_penalty: float
    runtime_seconds: float
    script_path: str | None = None
    report_path: str | None = None


@dataclass
class MultiSeedResult:
    """Aggregated outcome of running ``K`` seeds."""

    best_result: OptimizationResult
    ranked_results: list[OptimizationResult]
    records: list[CandidateRecord]
    manifest_path: Path | None = None


class MultiSeedRunner:
    """Executes and ranks multiple deterministic placement seeds."""

    def __init__(
        self,
        board: BoardModel,
        polish_config: PolishConfig,
        mode: PlacementMode = "polish",
    ) -> None:
        self.board = board
        self.polish_config = polish_config
        self.mode = mode

    def run(
        self,
        num_candidates: int = 1,
        output_dir: str | Path | None = None,
        keep_all_candidates: bool = False,
    ) -> MultiSeedResult:
        """Run ``num_candidates`` sequential seeds and rank by quality."""
        k = max(1, num_candidates)
        raw_results: list[OptimizationResult] = []

        for idx in range(k):
            seed = self.polish_config.seed + idx
            cfg = replace(self.polish_config, seed=seed)
            starting_state = None
            if self.mode == "place":
                coarse_cfg = CoarseConfig(
                    grid_mm=cfg.grid_mm,
                    seed=seed,
                    edge_clearance_mm=cfg.edge_clearance_mm,
                    allow_mirror=cfg.allow_mirror,
                    mirrorable_names=cfg.mirrorable_names,
                    cost_config=cfg.cost_config,
                )
                starting_state = CoarsePlacer(self.board, coarse_cfg).place_coarse()

            res = LocalPolishOptimizer(self.board, cfg).optimize(
                starting_state=starting_state
            )
            raw_results.append(res)

        ranked = sorted(
            raw_results,
            key=lambda r: (
                len(r.final_violations),
                r.best_cost.total_cost,
                r.best_cost.airwire_crossings,
                r.best_cost.weighted_mst_wirelength_mm,
            ),
        )

        emitter = EagleScriptEmitter()
        out_dir = (
            Path(output_dir).resolve()
            if output_dir is not None
            else self.board.source_path.parent / "placer"
        )
        records: list[CandidateRecord] = []
        manifest_path: Path | None = None

        if k > 1 or keep_all_candidates:
            cand_dir = out_dir / "candidates"
            if keep_all_candidates:
                cand_dir.mkdir(parents=True, exist_ok=True)
            for rank_idx, res in enumerate(ranked, start=1):
                scr_p: str | None = None
                rep_p: str | None = None
                if keep_all_candidates:
                    stem = f"{self.board.source_path.stem}_cand{rank_idx:02d}_seed{res.seed}"
                    s_path = cand_dir / f"{stem}.scr"
                    r_path = cand_dir / f"{stem}.json"
                    s_path.write_text(
                        emitter.render_script(self.board, res), encoding="utf-8"
                    )
                    r_path.write_text(
                        json.dumps(
                            emitter.build_report(self.board, res, script_path=s_path),
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    scr_p = str(s_path)
                    rep_p = str(r_path)

                records.append(
                    CandidateRecord(
                        rank=rank_idx,
                        seed=res.seed,
                        mode=self.mode,
                        passed_audit=len(res.final_violations) == 0,
                        violation_count=len(res.final_violations),
                        total_cost=round(res.best_cost.total_cost, 4),
                        weighted_mst_wirelength_mm=round(
                            res.best_cost.weighted_mst_wirelength_mm, 4
                        ),
                        raw_mst_wirelength_mm=round(
                            res.best_cost.raw_mst_wirelength_mm, 4
                        ),
                        airwire_crossings=res.best_cost.airwire_crossings,
                        congestion_penalty=round(res.best_cost.congestion_penalty, 4),
                        runtime_seconds=round(res.runtime_seconds, 4),
                        script_path=scr_p,
                        report_path=rep_p,
                    )
                )

            out_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = out_dir / "candidates_manifest.json"
            manifest = {
                "tool": "eagle6-placer",
                "version": __version__,
                "source_board": str(self.board.source_path),
                "mode": self.mode,
                "candidate_count": len(records),
                "candidates": [asdict(rec) for rec in records],
            }
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )

        return MultiSeedResult(
            best_result=ranked[0],
            ranked_results=ranked,
            records=records,
            manifest_path=manifest_path,
        )
