# Worklog — 2026-11-25 (Phase 2 Complete: M2.1–M2.5 & `v0.2.0-phase2`)

- **Date:** 2026-11-25
- **Time:** 21:05 MST (-07:00)
- **Agent:** Antigravity
- **User:** beattidp

## Summary of Activity
- **M2.1 (Congestion Grid):** Added 2D grid airwire congestion penalty (`--congestion-weight`) to `cost.py` and unit tests in `tests/test_cost.py`.
- **M2.2 (Opt-In Mirroring):** Added `selection.py` (`expand_part_specs`, `resolve_mirrorable_components`), `--allow-mirror [PART_SPEC ...]`, `--restrict-mirror PART_SPEC ...`, SA side-flip move operator, and `MIRROR` + `ROTATE` + `MOVE` script emission. Verified Top→Bottom and Bottom→Top flips in real CadSoft EAGLE v6.6.0 via `eagle6-mcp` `validate_edit_script` (0 DRC errors).
- **M2.3 (Coarse-to-Fine `place`):** Implemented `coarse.py` (`ForceDirectedPlacer` + descending-area spiral `OverlapLegalizer`), added `eagle6-placer place` subcommand, and added synthetic fixture `tests/fixtures/unplaced_fresh.brd`. Verified 18→0 crossings, 7→0 violations, and 0 DRC errors in EAGLE v6.6.0.
- **M2.4 (Multi-Seed Candidates):** Implemented `candidates.py` (`MultiSeedRunner`, `--candidates K`, `--keep-all-candidates`, decoupled `candidates_manifest.json`).
- **M2.5 (Docs & Release):** Bumped version to `0.2.0`, hashed & saved walkthrough preview `doc/walkthroughs/img/unplaced_fresh_preview_ad483ccb.png`, updated `doc/user-manual.md`, `README.md`, `doc/features/03_phase2-coarse-mirror-congestion.md`, `doc/walkthroughs/2026-11-25_phase2-coarse-place.md`, and `STATE.md`. All **40 tests pass**.
