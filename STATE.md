# Project State & Session Handoff
*Last Updated: 2026-11-25 21:05 MST (-07:00)*

## 🎯 Current Goal
- **Phase 2 (`v0.2.0-phase2`) is complete and verified** (40 passing tests): 2D congestion grid, opt-in `--allow-mirror`/`--restrict-mirror` with range syntax, coarse-to-fine `eagle6-placer place`, and multi-seed `--candidates K` with decoupled `candidates_manifest.json`.

## ✅ Completed Recently
- **Phase 2 (M2.1–M2.5) Complete (`v0.2.0-phase2`):**
  - M2.1: 2D routing congestion grid penalty (`cost.py`, `--congestion-weight`).
  - M2.2: `--allow-mirror [SPEC ...]` / `--restrict-mirror SPEC ...` (`selection.py`, `constraints.py`, `optimizer.py`, `emitter.py`) with verified EAGLE v6.6.0 `MIRROR`/`ROTATE`/`MOVE` output.
  - M2.3: Coarse-to-fine `eagle6-placer place` (`coarse.py`) + synthetic `tests/fixtures/unplaced_fresh.brd` (`18 → 0` crossings, `7 → 0` violations, `0` DRC errors in EAGLE v6.6.0).
  - M2.4: Multi-seed `--candidates K` + `--keep-all-candidates` + `candidates_manifest.json` (`candidates.py`).
  - M2.5: Updated `doc/user-manual.md`, `README.md`, `doc/features/03_phase2-coarse-mirror-congestion.md`, `doc/walkthroughs/2026-11-25_phase2-coarse-place.md` (with hashed `img/unplaced_fresh_preview_ad483ccb.png`), and `doc/worklogs/2026-11-25_phase2-complete.md`.

## 🚧 In Progress / Blockers
- Local git history and tags (`v0.1.0-phase1`, `v0.1.1-phase1`, `v0.2.0-phase2`) ready for user review before pushing upstream.

## ⏭️ Exact Next Step
1. Review commit log for upstream push, test Phase 2 features (`--allow-mirror`, `--candidates 3`, or `place`) on real boards, or begin Phase 3 planning (decoupled `eagle6-placer-mcp` server).

## 📂 Active Files (Do Not Scan Outside These First)
- `STATE.md`
- `README.md`
- `doc/user-manual.md`
- `doc/features/03_phase2-coarse-mirror-congestion.md`
- `doc/walkthroughs/2026-11-25_phase2-coarse-place.md`
- `src/eagle6_placer/cli.py`
