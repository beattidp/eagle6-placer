---
name: placer-bridge
description: Domain workflow for optimizing unlocked component placement on CadSoft EAGLE v6.6.0 boards (.brd) for improved routability, emitting human-reviewable EAGLE .scr scripts, and verifying results with eagle6-mcp and eagle6-freerouting.
---

# EAGLE v6 Auto-Placement (`eagle6-placer`) Workflow

## End-to-End Pipeline
1. **Pre-Placement Audit (via `eagle6-mcp`):**
   - Inspect board dimensions, existing component placement (`locked="yes"` vs. unlocked elements), routing status, and design rules (`get_board_summary`, `get_board_placement`, `get_board_routing_status`, `get_design_rules`).
   - Verify `.sch` ↔ `.brd` consistency (`check_sch_brd_consistency`) and confirm that connectors, mounting holes, and mechanically constrained parts are marked `locked="yes"` before optimizing.
   - Note any existing routed copper on unlocked parts (placement optimization should target unrouted boards or ripped-up regions).
2. **Parse EAGLE `.brd` & Extract Placement Constraints:**
   - Preserve exact millimeter coordinates (EAGLE v6 XML stores all coordinates in `mm`), board outline (layer `20` `Dimension`), edge clearance (`mdCopperDimension`), mechanical `Hole` primitives, and keepouts (`tKeepout` layer `39`, `bKeepout` layer `40`, `tRestrict`/`bRestrict` layers `41`/`42`).
   - Treat every element with `locked="yes"` as an immobile anchor.
   - Derive component courtyards from package `tKeepout`/`bKeepout` layers, falling back to the union of `pads`/`smds` + `tPlace` silkscreen + configurable courtyard margin (THT footprints block both top and bottom sides; SMD footprints block only their own side).
3. **Optimize Unlocked Component Placement:**
   - Support both **polish mode** (local nudges, `90°` rotations, and pairwise swaps with an optional displacement penalty) and **coarse-to-fine mode** (force-directed initial placement + overlap legalization followed by Simulated Annealing / local search).
   - Enforce hard constraints: locked parts immobile, courtyards inside board outline minus edge clearance, zero same-side courtyard overlap, keepout/hole avoidance, placement grid snapping, and allowed rotations (`R0`/`R90`/`R180`/`R270`, optional bottom-side mirror `M*`).
   - Optimize a pin-accurate routability objective: transformed pad-to-pad wirelength (MST or HPWL), airwire crossing count, and routing congestion/density—excluding or down-weighting global pour nets (`GND`, `VCC`, etc.) while supporting optional functional proximity groups (e.g., decoupling caps near IC power pins, crystals near MCUs).
4. **Emit Human-Reviewable EAGLE `.scr` Script:**
   - Never mutate `.brd` or `.sch` XML files on disk.
   - Emit commented `.scr` commands (`GRID MM;`, `MIRROR <name>;` if side changed, `ROTATE =R<angle> <name>;` or `ROTATE =MR<angle> <name>;`, `MOVE <name> (<x> <y>);`, and `RATSNEST;`) along with a structured JSON before/after metrics report.
5. **Post-Placement Verification (via `eagle6-mcp` & Optional `eagle6-freerouting`):**
   - Dry-run the generated placement `.scr` on a staged copy using `eagle6-mcp`'s `validate_edit_script`.
   - Run `run_drc(render_overlay=True)` and `render_board` to verify zero new DRC/overlap errors and visually inspect the updated layout.
   - Optionally evaluate top-$K$ candidate placements through headless `eagle6-freerouting` (`route_board`) to rank by actual routing outcomes (unrouted airwires, DRC errors, via count, trace length) before instructing the user to run `SCRIPT '<path>';` in EAGLE GUI with full Undo support.
