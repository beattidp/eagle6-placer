---
name: eagle6-placer
description: End-to-end component auto-placement workflow for CadSoft EAGLE v6.6.0 boards (.brd) using the eagle6-placer MCP server (audit_placement, polish_board, place_board) chained with eagle6-mcp for staged .scr/DRC validation and optional eagle6-freerouting closed-loop candidate ranking.
---

# EAGLE v6 Component Auto-Placement (`eagle6-placer`) Workflow

## End-to-End Pipeline
1. **Pre-Placement Audit:**
   - Call `eagle6-placer`'s `audit_placement(brd_path)` (and optionally `eagle6-mcp`'s `check_sch_brd_consistency`) to inspect board dimensions, `locked="yes"` anchors, unlocked parts, routed-copper guard status, initial MST wirelength, airwire crossings, congestion, and any pre-existing courtyard/hole violations.
   - Confirm that connectors, mounting holes, and mechanically constrained parts are marked `locked="yes"` before optimizing.
2. **Choose Mode & Optimize (`polish_board` or `place_board`):**
   - Use **`polish_board`** when unlocked parts are already positioned on the board and need local untangling, orientation polish, and overlap legalization (default `displacement_weight=0.1`).
   - Use **`place_board`** when unlocked parts start off-board (fresh Schematic → Board) or are badly scattered (force-directed analytical placement → spiral overlap legalization → SA refinement, default `displacement_weight=0.0`).
   - Pass `proximity_groups` (e.g. `[["U1", "C1", "C2"]]`) to keep decoupling capacitors, crystals, or sense resistors close to their target ICs.
   - Keep-side is the default. To allow Top↔Bottom flipping for unlocked **SMD-only** parts, set `allow_mirror=True` (optionally scoped with `allow_mirror_specs=["{C1..C12}"]` and/or `restrict_mirror_specs=["U1,IC3"]`).
   - Enable `preview=True` (with `tPlace`/`bPlace` silkscreen active by default; `hide_place=True` to hide) to generate Before/After SVG/PNG comparisons.
3. **Staged Dry-Run Verification (via `eagle6-mcp`):**
   - Pass the returned `script_content` into `eagle6-mcp`'s `validate_edit_script(project_path=brd_path, script_content=..., run_checks=True)` to execute it inside headless EAGLE v6.6.0 on an isolated staged copy and confirm zero new DRC errors and exact placement deltas.
4. **Optional Closed-Loop Candidate Ranking (via `eagle6-freerouting`):**
   - Run `polish_board` or `place_board` with `candidates=3` (or `5`) and `keep_all_candidates=True` to emit `candidates_manifest.json` and `candidates/*.scr`.
   - Dry-run top candidates via `eagle6-mcp` and benchmark actual routing outcomes (unrouted airwires, DRC errors, via count, trace length) via `eagle6-freerouting`'s `route_board` to select the winning `.scr`.
5. **User GUI Application:**
   - Present the Before/After metrics, preview image, and DRC delta, then instruct the user to execute `SCRIPT '<script_path>';` inside CadSoft EAGLE v6.6.0 GUI with full Undo support.
