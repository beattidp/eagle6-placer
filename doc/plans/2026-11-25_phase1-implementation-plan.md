# Phase 1 Implementation Plan — `eagle6-placer` (Local Polish MVP)

*Date: 2026-11-25*
*Scope: Local polish mode, keep-side default, synthetic EAGLE v6 `.brd` fixtures, CLI, `.scr` + JSON emitter, and staged verification via `eagle6-mcp`.*

---

## Goals & Exit Criteria
Phase 1 is complete when:
1. `eagle6-placer polish <board.brd>` parses valid CadSoft EAGLE v6.6.0 XML `.brd` files without modifying them.
2. Locked components (`locked="yes"`), board-side assignments (`top`/`bottom`), board outline clearances, keepouts/holes, and zero same-side courtyard overlaps (including dual-side THT blocking) are strictly enforced.
3. The Simulated Annealing local polish engine demonstrably reduces pin-accurate MST wirelength and airwire crossings on synthetic `.brd` fixtures (and real candidate boards when available).
4. Emitted `.scr` scripts pass `eagle6-mcp`'s `validate_edit_script` + `run_drc` with zero new DRC/overlap errors and clean visual inspection via `render_board`.
5. All unit and regression tests pass under the `eagle6-placer` pyenv virtualenv.

---

## Milestones

### Milestone 0: Project Scaffolding & Python Environment
**Deliverables:**
- `pyproject.toml` (package metadata, `src/` layout, `eagle6-placer` console script entry point, `pytest` config).
- `README.md` (concise project overview, quickstart, safety model).
- `src/eagle6_placer/__init__.py` package skeleton.
- `tests/` directory with `tests/conftest.py` and `tests/fixtures/`.
- Verify/activate `eagle6-placer` pyenv virtualenv (per `/python` skill), install `pytest` (and editable package `pip install -e .`), and refresh `requirements.txt` with `>=` constraints.

### Milestone 1: Synthetic EAGLE v6.6.0 `.brd` Test Fixtures
Create two minimal, well-formed EAGLE v6.6.0 XML `.brd` files in `tests/fixtures/` (valid enough to load cleanly in both `eagle6-placer` and `eagle6-mcp` / EAGLE v6.6.0):
1. **`tangled_polish.brd`** (50 × 40 mm rectangular board):
   - 2 locked edge connectors (`J1` left, `J2` right, `locked="yes"`).
   - 1 locked central IC (`U1`, `locked="yes"`).
   - 6–8 unlocked 0805 SMD passives (`R1`–`R4`, `C1`–`C4`) placed with deliberate swaps, suboptimal `90°`/`180°` rotations, and airwire crossings.
   - Purpose: Primary benchmark verifying wirelength & crossing reduction while keeping locked parts untouched.
2. **`mixed_tht_keepout.brd`** (60 × 45 mm board):
   - Locked mounting holes (`<hole>` in `<plain>`), a `tKeepout` zone (layer 39), bottom-side SMD components (`rot="MR0"`), THT components (`<pad>` footprints occupying both sides), and a `GND` polygon pour (`<signal name="GND"><polygon ...>`).
   - Purpose: Verifies keep-side preservation, mirror-aware pad/courtyard transforms, THT dual-side collision blocking, keepout/hole avoidance, and pour-net down-weighting.

### Milestone 2: Data Model, Geometry & `.brd` Parser
**Modules (`src/eagle6_placer/`):**
- `geometry.py`:
  - `Point2D`, `Rect2D`, `Segment2D` value objects.
  - `ElementTransform` (parses EAGLE `rot` strings `[M][S]R<angle>` and transforms local `(x, y)` and bounding boxes to board coordinates).
  - Exact 2D proper segment intersection test (for airwire crossings) and AABB/polygon containment & overlap helpers.
- `models.py`:
  - `Pin`, `Footprint`, `Component`, `Net`, `KeepoutRegion`, `Hole`, `BoardOutline`, `DesignRules`, `BoardModel`, `PlacementState`.
- `parser.py`:
  - `EagleBoardParser` (read-only `xml.etree.ElementTree` parser).
  - Parses `<designrules>` (`mdCopperDimension` with unit conversion `mil`/`mm`/`inch`), `<libraries>/<packages>` (courtyard from `tKeepout`/`bKeepout` or fallback from `pad`/`smd`/`hole`/`tPlace`/`bPlace` + margin), `<plain>` (layer 20 outline, holes, keepouts), `<elements>` (locked status, initial pose), and `<signals>` (pin connectivity, routed-copper detection, polygon-pour net detection).

**Tests (`tests/test_geometry.py`, `tests/test_parser.py`):**
- Verify all 8 orthogonal EAGLE transforms (`R0`–`R270`, `MR0`–`MR270`).
- Verify `mil`/`mm` unit parsing, THT vs. SMD side occupancy, locked flag parsing, keepout/hole extraction, and routed-copper detection on both fixtures.

### Milestone 3: Constraint Validator & Routability Cost Function
**Modules (`src/eagle6_placer/`):**
- `constraints.py`:
  - `ConstraintChecker`: validates single-component move feasibility and full-board legality (locked immutability, keep-side, board outline minus edge clearance, zero same-side / THT courtyard overlap, keepout & hole avoidance).
- `cost.py`:
  - `CostConfig` & `CostBreakdown` dataclasses.
  - `RoutabilityEvaluator`:
    - Pin-accurate Prim's MST wirelength per net with pour/global net down-weighting.
    - Non-pour MST edge crossing counter.
    - Displacement penalty from initial pose.
    - Optional proximity-group penalty.

**Tests (`tests/test_constraints.py`, `tests/test_cost.py`):**
- Boundary violation, same-side overlap, opposite-side SMD non-overlap, THT dual-side overlap, and keepout/hole rejection tests.
- Exact MST length and known-crossing-count unit tests.

### Milestone 4: Local Polish Simulated Annealing Engine
**Modules (`src/eagle6_placer/`):**
- `optimizer.py`:
  - `PolishConfig` & `OptimizationResult` dataclasses.
  - `LocalPolishOptimizer`:
    - Initial feasibility audit (warns/errors on routed unlocked parts unless `allow_routed=True`).
    - Deterministic seeded SA loop with grid-snapped local nudge, `90°` rotation, nudge+rotate, and same-side pairwise swap moves.
    - Strict hard-constraint rejection and best-feasible-state tracking.

**Tests (`tests/test_optimizer.py`):**
- Deterministic reproducibility test (same seed → identical result).
- Optimization improvement tests on `tangled_polish.brd` and `mixed_tht_keepout.brd`: assert lower total cost, lower MST wirelength / crossings, zero constraint violations, zero locked-part movement, and zero side flips.

### Milestone 5: `.scr` Emitter, JSON Reporter, CLI & Staged Verification
**Modules (`src/eagle6_placer/`):**
- `emitter.py`:
  - `EagleScriptEmitter`: generates commented EAGLE v6 `.scr` (`GRID MM;`, `ROTATE =...`, `MOVE ...`, `RATSNEST;`, `GRID LAST;`) for changed unlocked components only, plus structured JSON metrics report.
- `cli.py`:
  - `argparse`-based CLI (`eagle6-placer polish <board.brd> ...`) with clean exit codes and human-readable summary table.

**Tests & Verification (`tests/test_emitter.py`, `tests/test_cli.py`):**
- Verify `.scr` formatting (exact EAGLE `=R*`/`=MR*` syntax, unchanged parts omitted, locked parts never emitted).
- End-to-end CLI run on both synthetic fixtures.
- Staged dry-run validation of the generated `.scr` on `tangled_polish.brd` using `eagle6-mcp` (`validate_edit_script` + `run_drc` + `render_board`).

---

## Architecture Dependency Graph
```
cli.py
 ├── parser.py ──▶ models.py ──▶ geometry.py
 ├── optimizer.py
 │    ├── constraints.py ──▶ models.py, geometry.py
 │    └── cost.py        ──▶ models.py, geometry.py
 └── emitter.py ──▶ models.py
```

---

## Risks & Mitigations
- **EAGLE v6 `rot` mirror+rotation order ambiguity:** Validate our `ElementTransform` math against `eagle6-mcp`'s `get_board_placement` / `render_board` on a mirrored fixture (`MR90`, `MR270`) in Milestone 1/2 so transformed pad coordinates match EAGLE v6.6.0 exactly.
- **Initial board already has minor courtyard overlaps:** If a user's existing `.brd` starts with an overlap on an unlocked part, the constraint checker should allow moves that strictly *reduce* overlap count on that part (or log a clear warning) rather than locking up the optimizer. We will handle this cleanly in Milestone 3/4.
- **Non-rectangular board outlines:** Support polygon containment from the start (ray-casting + edge distance) while fast-pathing axis-aligned rectangles.
