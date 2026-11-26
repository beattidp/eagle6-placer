# 02 — Phase 1.1 Refinements: Soft Overlap Legalization, Pour-Net Via Tolerance & Built-In Preview

## Overview
Based on benchmarking Phase 1 on a real 41-component EAGLE v6.6.0 board (`prpp-mcu.brd`), Phase 1.1 adds three high-impact usability and quality refinements while keeping all core safety invariants intact.

## Features Implemented
1. **Soft Overlap-Legalization Penalty (`constraints.py`, `cost.py`, `optimizer.py`):**
   - When an input board already contains pre-existing courtyard/hole/keepout overlaps, the optimizer tracks total soft violations and applies `--overlap-penalty` (default `250.0` per violation) to the objective.
   - Absolute hard invariants (`locked="yes"` immutability, keep-side, and layer 20 board outline minus edge clearance) remain strictly unbreakable at every step.
   - Moves are never allowed to increase violation count; once violations drop to `0`, zero-overlap becomes a strict invariant for the rest of the run.
2. **Default Pour-Net Via Tolerance (`models.py`, `optimizer.py`, `cli.py`):**
   - `BoardModel.routed_unlocked_components(ignore_pour_nets=True)` ignores `<via>`/`<wire>` copper on nets containing a copper-pour `<polygon>` (e.g. `GND`/`VMOT` thermal or stitching vias) by default, while still aborting with `RoutedCopperError` on routed signal nets unless `--allow-routed` is specified.
   - Pass `--strict-routed` to block on pour-net copper as well.
3. **Built-In Before/After `--preview` Renderer (`preview.py`, `models.py`, `parser.py`, `cli.py`):**
   - Extracts package-local `tPlace` (layer 21) and `bPlace` (layer 22) `<wire>`, `<rectangle>`, and `<circle>` silkscreen geometry into `Footprint`.
   - `eagle6-placer polish <board.brd> --preview` writes `<stem>_preview.svg` (and `<stem>_preview.png` via ImageMagick `convert`/`magick` when available), fitting the entire board cleanly at high resolution (`18 px/mm`) with `tPlace`/`bPlace` silkscreen active by default.
   - Pass `--hide-place` to hide silkscreen layers and render courtyards + pads + airwires only.

## Verification
- `pytest -v`: **33 passed** (4 new tests covering soft overlap legalization, pour-net via tolerance vs. strict mode, and `--preview` with/without `tPlace`/`bPlace`).
- Real board (`prpp-mcu.brd`, seed 42, 6000 steps): Overlaps `13 → 0` (`PASS`), Weighted MST `513.21 → 436.60 mm` (-14.9%), Raw MST `765.90 → 659.38 mm` (-13.9%), Crossings `62 → 30` (-51.6%), and `validate_edit_script` in EAGLE v6.6.0 passed with **0 new DRC errors**.
