# 01 — Phase 1 Local Polish MVP (`eagle6-placer`)

## Overview
Phase 1 implements a standalone, read-only CadSoft EAGLE v6.6.0 `.brd` placement polisher operating in **local polish mode** with **keep-side default**. It optimizes unlocked component positions and `90°` orientations for improved routability and emits human-reviewable EAGLE `.scr` scripts plus JSON metrics reports.

## Architecture & Modules (`src/eagle6_placer/`)
- **`geometry.py`:** `Point2D`, `Rect2D`, `Segment2D`, `ElementTransform` (exact EAGLE v6 `[M][S]R<angle>` transform: mirror local X → CCW rotate → translate), 2D proper segment intersection, and ray-casting polygon containment.
- **`models.py`:** Immutable board domain model (`Pin`, `Footprint`, `Component`, `ContactRef`, `Net`, `KeepoutRegion`, `BoardHole`, `DesignRules`, `BoardOutline`, `BoardModel`) and mutable `PlacementState`.
- **`parser.py`:** Read-only `EagleBoardParser` extracting layer 20 (`Dimension`) outlines, `<designrules>` (`mdCopperDimension` with `mil`/`mm`/`inch`/`um` conversion), package courtyards (`tKeepout`/`bKeepout` with fallback to `pad`/`smd`/`hole`/`tPlace`/`bPlace` + margin), THT dual-side occupancy, locked status, routed copper, and copper-pour nets.
- **`constraints.py`:** `ConstraintChecker` enforcing locked immutability, keep-side, outline minus edge clearance, zero same-side / dual-side THT courtyard overlap, and keepout/hole avoidance.
- **`cost.py`:** `RoutabilityEvaluator` computing pin-accurate Euclidean Prim's MST wirelength (with pour/global net down-weighting), non-pour airwire crossing count, displacement penalty, and optional proximity groups.
- **`optimizer.py`:** Deterministic seeded `LocalPolishOptimizer` (Simulated Annealing over grid-snapped nudges, `90°` rotations, nudge+rotate, and same-side pairwise swaps, plus a final greedy orientation pass and `RoutedCopperError` guard).
- **`emitter.py`:** `EagleScriptEmitter` outputting commented `.scr` (`GRID MM;`, `ROTATE =<rot> '<name>';`, `MOVE '<name>' (<x> <y>);`, `RATSNEST;`, `GRID LAST;`) for changed unlocked parts only, plus structured JSON report.
- **`cli.py`:** `eagle6-placer polish <board.brd> [options]` console entry point.

## CLI Usage
```bash
eagle6-placer polish path/to/board.brd \
  --output-dir path/to/out \
  --grid-mm 0.5 \
  --steps 4000 \
  --seed 42
```

## Bug Identified & Fixed During Verification
- **Bug:** During staged execution of generated `.scr` scripts in CadSoft EAGLE v6.6.0 via `eagle6-mcp`'s `validate_edit_script`, unquoted `ROTATE =R0 R1;` commands left `R1`–`R4` at `R180`, while `ROTATE =R0 C2;` succeeded.
- **Root Cause:** CadSoft EAGLE v6's `ROTATE` command parser interprets unquoted resistor designators starting with `R` followed by digits (`R1`, `R2`, `R3`, `R4`) as rotation-angle tokens (`1°`, `2°`, etc.) rather than element names.
- **Fix & Rationale:** `EagleScriptEmitter.render_script` now always single-quotes component designators (`ROTATE =R0 'R1';`, `MOVE 'R1' (x y);`), which EAGLE v6 unambiguously parses as element names.
- **Regression Test:** Added assertion in `tests/test_emitter.py` verifying all emitted `MOVE`/`ROTATE` commands single-quote element names, and verified both `R*` and bottom-side `MR*` rotations in real EAGLE v6.6.0 via `validate_edit_script`.

## Verification Results (Synthetic Fixtures)
- **Unit & Integration Suite:** `29 passed` in `pytest -v`.
- **`tangled_polish.brd` (seed 42, 4000 steps):**
  - Weighted MST: `157.35 mm -> 69.74 mm` (-55.7%)
  - Raw MST: `259.97 mm -> 146.69 mm` (-43.6%)
  - Airwire crossings: `12 -> 0`
  - `eagle6-mcp` `validate_edit_script` + DRC: `success=true`, `errors_before=0`, `errors_after=0`, all 6 unlocked components moved/rotated accurately.
- **`mixed_tht_keepout.brd` (seed 7, 4000 steps):**
  - Weighted MST: `184.83 mm -> 44.05 mm` (-76.2%)
  - Raw MST: `251.17 mm -> 91.49 mm` (-63.6%)
  - Airwire crossings: `6 -> 0`
  - `eagle6-mcp` `validate_edit_script` + DRC: `success=true`, `errors_before=0`, `errors_after=0`, bottom-side `MR0 -> MR180` and THT `R180 -> R0` applied accurately.
