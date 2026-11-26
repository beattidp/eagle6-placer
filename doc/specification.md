# `eagle6-placer` Technical Specification

## 1. Purpose & Architecture
`eagle6-placer` is a standalone Python CLI and library for optimizing the placement and orientation of **unlocked** components (`locked != "yes"`) on **CadSoft EAGLE v6.6.0** XML `.brd` files.

It operates strictly read-only on `.brd` inputs and emits human-reviewable EAGLE `.scr` scripts plus structured JSON metrics reports. Verification (staged dry-run, DRC, board rendering) is delegated to the decoupled sibling tool `eagle6-mcp`, and optional post-placement autorouting evaluation is delegated to `eagle6-freerouting`.

---

## 2. EAGLE v6.6.0 Board Model & Geometry

### 2.1 Coordinate System & Units
- CadSoft EAGLE v6 XML stores all board, package, pad, SMD, wire, and hole coordinates in **millimeters (`mm`)**.
- All internal geometry and optimization calculations operate in `mm`.

### 2.2 Element Transform Semantics (`rot`)
In EAGLE v6 `.brd` XML, an `<element name="R1" x="ex" y="ey" rot="...">` carries an optional `rot` attribute matching `^[M]?[S]?R([0-9]+(?:\.[0-9]+)?)$` (default `"R0"`):
- `M` (mirror / bottom side): reflects package-local coordinates across the Y-axis (`x -> -x`, `y -> y`).
- `R<theta>`: rotates counter-clockwise by `theta` degrees around the package origin.
- `S` (spin): affects silkscreen text orientation only; does not alter copper or courtyard geometry.
- Translation: adds `(ex, ey)` to obtain board coordinates.

All pin coordinates and component courtyards are transformed using this exact package-to-board transform.

### 2.3 Board Outline, Edge Clearance & Obstacles
- **Board Outline:** Extracted from `<plain>` wires/polygons on layer `20` (`Dimension`). Phase 1 supports axis-aligned rectangular and general closed-polygon outlines (point-in-polygon + segment clearance checks).
- **Edge Clearance:** Extracted from `<designrules>` parameter `mdCopperDimension` (converted to `mm`, e.g., `40mil -> 1.016 mm`), with a CLI override (`--edge-clearance-mm`) and safe fallback (`0.5 mm`).
- **Keepouts & Holes:** Extracted from `<plain>` `<hole>` primitives and `<rectangle>`/`<polygon>`/`<wire>` regions on `tKeepout` (layer `39`), `bKeepout` (layer `40`), `tRestrict` (layer `41`), and `bRestrict` (layer `42`).

### 2.4 Component Courtyards & Side Occupancy
For each referenced `<package>` in `<libraries>`:
1. **Primary Courtyard:** Bounding box of package shapes on `tKeepout` (layer `39`) / `bKeepout` (layer `40`) if present.
2. **Fallback Courtyard:** Union bounding box of all package `<pad>` (diameter or drill + annular ring), `<smd>` (`dx`, `dy`, local `rot`), `<hole>`, and `tPlace` (layer `21`) / `bPlace` (layer `22`) geometry, expanded uniformly by `courtyard_margin_mm` (default `0.25 mm`).
3. **Side Occupancy:**
   - **SMD-only package** (no `<pad>` and no `<hole>`): occupies only its mounted side (`top` if unmirrored, `bottom` if mirrored `M`).
   - **THT / Mixed package** (contains any `<pad>` or `<hole>`): occupies **both** `top` and `bottom` sides.

### 2.5 Locked Parts & Routed Copper Guard
- Any `<element>` with `locked="yes"` is marked immobile (`is_locked=True`) and serves as a fixed anchor.
- Any `<signal>` containing `<wire>` or `<via>` elements is flagged as routed. If an unlocked component has pins belonging to a routed net, the optimizer warns and aborts by default unless `--allow-routed` is explicitly specified.

---

## 3. Phase 1 Optimization Specification (Local Polish Mode)

Phase 1 focuses on **local polish mode** with **keep-side default** (no top↔bottom mirroring).

### 3.1 Hard Constraints (Zero-Violation Invariant)
Every accepted placement state must satisfy:
1. **Locked immutability:** Locked elements retain exact initial `(x, y, rot)`.
2. **Keep-side (default):** Every unlocked element stays on its original side (`mirrored` flag unchanged).
3. **Board containment:** Every unlocked element's transformed courtyard lies completely inside the board outline inset by `edge_clearance_mm`.
4. **Zero courtyard overlap:** No two components sharing a board side (`top` or `bottom`, with THT occupying both) have overlapping courtyards.
5. **Keepout & hole avoidance:** No unlocked component courtyard overlaps a board-level mechanical `<hole>` or same-side keepout region.
6. **Grid & orientation snapping:** Coordinates snap to `grid_mm` (default `0.5 mm`); rotations are restricted to `{0°, 90°, 180°, 270°}` (preserving `M` prefix for bottom-side parts).

### 3.2 Routability Objective Function
Given placement state $P$, the scalar cost to minimize is:

$$J(P) = w_{\text{wl}} \cdot L_{\text{MST}}(P) + w_{\text{cross}} \cdot C_{\text{airwire}}(P) + w_{\text{disp}} \cdot D_{\text{anchor}}(P) + w_{\text{prox}} \cdot G_{\text{prox}}(P)$$

Where:
- **$L_{\text{MST}}(P)$ (Weighted Pin-Accurate MST Wirelength):** Sum over all multi-pin nets $n$ of $w_n \cdot \text{MST}(\text{pins}(n))$, where $\text{MST}$ is the Euclidean Minimum Spanning Tree length (Prim's algorithm) over exact transformed pad/SMD centers.
- **Pour / Global Net Down-Weighting ($w_n$):** Nets that contain a `<polygon>` copper pour in the `.brd` or match configurable power/ground patterns (`GND`, `AGND`, `DGND`, `VCC`, `VDD`, `3V3`, `5V`, etc.) or exceed a fanout threshold (e.g., $\ge 12$ pins) are assigned a low weight (`--pour-net-weight`, default `0.05`) so global pours do not distort signal-path optimization.
- **$C_{\text{airwire}}(P)$ (Airwire Crossings):** Count of proper 2D segment intersections between MST edges of distinct non-pour signal nets. Directly penalizes routing tangles and via pressure.
- **$D_{\text{anchor}}(P)$ (Displacement Penalty):** Sum of Euclidean distances $\|p_i - p_{i,0}\|_2$ from each unlocked component's initial position, keeping polish moves local to the designer's floorplan (controlled by `--displacement-weight`).
- **$G_{\text{prox}}(P)$ (Optional Proximity Groups):** Soft distance penalty for user-specified part groups (e.g., keeping decoupling capacitors adjacent to IC power pins).

### 3.3 Simulated Annealing (SA) Search Engine
- **Move Operators** (applied only to unlocked components):
  1. *Local Grid Nudge:* Translate by $(\Delta x, \Delta y)$ snapped to `grid_mm`, with step radius decaying with temperature.
  2. *Discrete Rotate:* Change orientation among `{0°, 90°, 180°, 270°}` (preserving side `M`).
  3. *Nudge + Rotate:* Combined local translation and `90°` rotation.
  4. *Pairwise Swap:* Exchange centers of two unlocked same-side components (useful for untangling adjacent passives).
- **Acceptance Criterion:** Moves violating any hard constraint are immediately rejected. Feasible moves are accepted if $\Delta J \le 0$ or with Metropolis probability $\exp(-\Delta J / T)$.
- **Determinism:** Controlled via `--seed` using a dedicated `random.Random(seed)` instance.
- **Best-State Tracking:** Always tracks and returns the lowest-cost feasible state observed during the run.

---

## 4. Outputs & CLI Interface

### 4.1 EAGLE `.scr` Script Output
Default path: `<board_dir>/placer/<board_stem>_placed.scr`.
- Contains header comments with source board path, seed, and before/after metrics.
- Emits `GRID MM;` followed by `ROTATE =R<angle> <name>;` (or `ROTATE =MR<angle> <name>;`) and `MOVE <name> (<x> <y>);` **only for unlocked elements whose position or rotation changed**.
- Ends with `RATSNEST;` and `GRID LAST;`.

### 4.2 JSON Metrics Report
Default path: `<board_dir>/placer/<board_stem>_placed.json`.
- Records configuration parameters, seed, runtime, before/after cost breakdown (`mst_wirelength_mm`, `airwire_crossings`, `total_displacement_mm`, `total_cost`), constraint audit status, and per-component move list.

### 4.3 CLI Entry Point
```bash
eagle6-placer polish <board.brd> \
  [--output-dir <dir>] \
  [--grid-mm 0.5] \
  [--courtyard-margin-mm 0.25] \
  [--edge-clearance-mm <auto>] \
  [--steps 5000] \
  [--seed 42] \
  [--displacement-weight 0.1] \
  [--crossing-weight 5.0] \
  [--pour-net-weight 0.05] \
  [--allow-routed]
```

---

## 5. Multi-Phase Roadmap
- **Phase 1 (Current):** Local polish mode, keep-side default, synthetic `.brd` test fixtures, CLI, `.scr` + JSON output, and staged `eagle6-mcp` validation.
- **Phase 2:** Coarse-to-fine placement (force-directed analytical placement + overlap legalization), optional double-sided mirroring (`--allow-mirror`), routing congestion grid term, and closed-loop top-$K$ candidate ranking via `eagle6-freerouting`.
- **Phase 3:** Decoupled MCP server (`eagle6-placer-mcp`) exposing placement optimization tools directly to AI agents.
