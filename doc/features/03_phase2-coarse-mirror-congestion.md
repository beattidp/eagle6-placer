# 03 — Phase 2: Congestion Grid, Double-Sided Mirroring, Coarse-to-Fine `place` & Multi-Seed Candidates

## Overview
Phase 2 (`v0.2.0-phase2`) extends `eagle6-placer` with four major capabilities while maintaining zero external runtime dependencies and zero code coupling with `eagle6-mcp` and `eagle6-freerouting`.

## Implemented Features
1. **2D Routing Congestion Grid (`cost.py`):**
   - Coarse `2.5 mm` grid measuring non-pour MST airwire demand per cell; quadratic excess penalty `(demand - capacity)^2` weighted by `--congestion-weight` (default `0.5`, set `0` to disable).
2. **Opt-In Double-Sided Mirroring (`selection.py`, `constraints.py`, `optimizer.py`, `emitter.py`, `cli.py`):**
   - Restricted strictly to unlocked **SMD-only** packages (locked parts and THT packages never mirror).
   - `--allow-mirror` (no args) enables mirroring for all unlocked SMDs.
   - `--allow-mirror <spec>` restricts mirroring to matching parts, supporting comma lists, bash brace expansion, and literal numeric ranges (`"{C1..C12},{C20..C30}"`, `R01..R08`).
   - `--restrict-mirror <spec>` excludes specific parts (e.g., `--allow-mirror --restrict-mirror U1,IC3`).
   - Emits `MIRROR '<name>';` followed by `ROTATE =<rot> '<name>';` and `MOVE '<name>' (x y);`, verified for both Top→Bottom and Bottom→Top flips in real CadSoft EAGLE v6.6.0 via `eagle6-mcp`'s `validate_edit_script`.
3. **Coarse-to-Fine Placement (`coarse.py`, `eagle6-placer place`):**
   - `ForceDirectedPlacer` runs damped spring relaxation around immobile `locked="yes"` anchors with short-range repulsion and board-boundary clamping.
   - `OverlapLegalizer` places unlocked footprints in descending courtyard-area order onto legal spiral grid-snapped slots.
   - Downstream `LocalPolishOptimizer` refines the legalized layout (`--displacement-weight 0.0` default in `place` mode) while recording deltas against the original `.brd`.
4. **Multi-Seed Candidate Exploration (`candidates.py`, `--candidates K`, `--keep-all-candidates`):**
   - Runs `K` deterministic seeds (`seed`, `seed + 1`, ..., `seed + K - 1`), ranks by `(violation_count, total_cost, airwire_crossings, weighted_mst)`, emits the winning `.scr`/`.json`/preview, and writes `candidates_manifest.json` (plus per-candidate `.scr`/`.json` files under `candidates/` when `--keep-all-candidates` is set) for decoupled closed-loop autorouting ranking via `eagle6-mcp` + `eagle6-freerouting`.

## Verification
- `pytest -v`: **40 passed**.
- Staged EAGLE v6.6.0 `validate_edit_script` + DRC verified:
  - `mixed_tht_keepout.brd` side-flip script (`C1` `R180 → MR90`, `R1` `MR0 → R270`): `exit_code=0`, 0 DRC errors.
  - `unplaced_fresh.brd` (`eagle6-placer place --candidates 3`): Weighted MST `236.62 → 70.18 mm` (-70.3%), crossings `18 → 0`, congestion `2.00 → 0.00`, overlaps `7 → 0`, 0 DRC errors.
