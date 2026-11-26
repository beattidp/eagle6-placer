# `eagle6-placer` User Manual

## 1. Introduction & Safety Model
`eagle6-placer` is a standalone Linux component auto-placement optimizer for **CadSoft EAGLE v6.6.0** XML board files (`.brd`). It improves PCB routability by optimizing the positions and `90°` orientations of **unlocked** components while keeping mechanically constrained parts strictly immobile.

### Core Safety Invariants
1. **Read-Only `.brd` Access:** `eagle6-placer` never writes to or mutates your `.brd` or `.sch` XML files. Direct XML editing can break CadSoft EAGLE v6 forward/back-annotation.
2. **Script-First Output (`.scr`):** Every placement change is emitted as a human-reviewable EAGLE script (`GRID MM;`, `ROTATE =... '<name>';`, `MOVE '<name>' (x y);`, `RATSNEST;`, `GRID LAST;`) that you execute inside EAGLE GUI with full **Undo** support.
3. **Locked Parts Are Sacred:** Any `<element>` with `locked="yes"` is treated as an immobile anchor and will never be moved, rotated, or mirrored.
4. **Keep-Side Default:** Top-side parts stay on Top (`R0`–`R270`), and bottom-side parts stay on Bottom (`MR0`–`MR270`).
5. **Routed Copper Guard:** By default, `eagle6-placer` refuses to move unlocked components attached to already-routed **signal** nets unless you pass `--allow-routed`. Existing vias/stubs on copper-pour nets (`<polygon>` pours such as `GND` or `VMOT`) are tolerated by default (pass `--strict-routed` to block on those too).

---

## 2. Installation & Requirements

### Requirements
- **OS:** Linux
- **Python:** 3.10 or newer (developed and tested on Python 3.13 via `pyenv`)
- **Runtime Dependencies:** Pure Python standard library (zero external runtime packages required)
- **Optional (for PNG previews):** ImageMagick (`convert` or `magick`) to automatically rasterize `_preview.svg` to `_preview.png`

### Install from Source
```bash
git clone <repo-url> eagle6-placer
cd eagle6-placer

# Activate your virtualenv (e.g., pyenv virtualenv eagle6-placer)
pip install -e .
pyenv rehash   # if using pyenv shims
```

Verify installation:
```bash
eagle6-placer --version
```

---

## 3. Preparing Your Board in EAGLE v6.6.0
Before running `eagle6-placer`:
1. **Lock mechanically fixed parts** in EAGLE Board Editor using the `LOCK` tool (connectors, mounting holes, switches, LEDs, heatsinks, or any IC whose position is fixed).
2. **Ensure a closed layer `20` (`Dimension`) board outline** exists.
3. **Rip up routed signal traces** on unlocked components you want to optimize (keep power/ground `<polygon>` pours and thermal vias if desired—they are tolerated by default).
4. **Save** the `.brd` file in EAGLE v6 XML format.

---

## 4. Quickstart

### Basic Local Polish with Before/After Preview
```bash
eagle6-placer polish path/to/my_board.brd --preview
```
By default, outputs are written to `path/to/placer/`:
- `my_board_placed.scr` — EAGLE v6.6.0 placement script
- `my_board_placed.json` — Structured before/after metrics and constraint audit report
- `my_board_preview.svg` — Full-board vector Before/After visual comparison (`tPlace`/`bPlace` silkscreen active)
- `my_board_preview.png` — Rasterized PNG preview (when ImageMagick is installed)

### Polishing with Functional Proximity Groups
```bash
eagle6-placer polish path/to/my_board.brd \
  --preview \
  --steps 6000 \
  --seed 42 \
  --proximity-group U1,C1,C2 \
  --proximity-group U3,C10,C11,R14,R15
```

---

## 5. CLI Reference (`eagle6-placer polish`)

```text
eagle6-placer polish <board.brd> [OPTIONS]
```

| Option | Default | Description |
| :--- | :--- | :--- |
| `board` | *(required)* | Path to input CadSoft EAGLE v6.6.0 `.brd` file (read-only). |
| `--output-dir DIR` | `<board_dir>/placer` | Directory where `.scr`, `.json`, and preview files are written. |
| `--grid-mm FLOAT` | `0.5` | Placement snap grid in millimeters (`0.25`, `0.5`, `1.27`, etc.). |
| `--courtyard-margin-mm FLOAT` | `0.25` | Uniform expansion (mm) around fallback courtyards for packages lacking explicit `tKeepout`/`bKeepout` shapes. |
| `--edge-clearance-mm FLOAT` | *(from `.brd`)* | Override copper-to-board-edge clearance in mm (defaults to `mdCopperDimension` in `<designrules>`, or `0.5` mm). |
| `--steps INT` | `4000` | Number of Simulated Annealing iterations (use `6000`–`10000` for denser 30–60+ part boards). |
| `--seed INT` | `42` | Deterministic PRNG seed for reproducible runs. |
| `--displacement-weight FLOAT` | `0.1` | Penalty per mm moved from initial placement. Increase (`0.5`–`1.0`) to keep changes tighter to your original floorplan. |
| `--crossing-weight FLOAT` | `5.0` | Penalty per airwire crossing between distinct non-pour signal nets. |
| `--pour-net-weight FLOAT` | `0.05` | Wirelength weight for copper-pour / global power nets (`GND`, `VCC`, `3V3`, `5V`, high-fanout nets, or `<polygon>` nets). |
| `--overlap-penalty FLOAT` | `250.0` | Soft penalty per pre-existing courtyard/hole overlap during legalization. |
| `--proximity-group PARTS` | *(none)* | Comma-separated component names to pull close together (repeatable, e.g., `--proximity-group U1,C1,C2`). |
| `--allow-routed` | `False` | Allow optimizing unlocked components attached to already-routed signal nets. |
| `--strict-routed` | `False` | Block even if routed copper/vias exist only on copper-pour nets (`GND`, `VMOT`, etc.). |
| `--preview` | `False` | Emit side-by-side Before/After `_preview.svg` (and `_preview.png` if ImageMagick is installed). |
| `--hide-place` | `False` | Hide `tPlace` (layer 21) and `bPlace` (layer 22) silkscreen outlines in `--preview` output. |

### Exit Codes
- `0`: Optimization succeeded and the final placement passed the constraint audit (`0` violations).
- `1`: Optimization completed, but one or more constraint violations remained in the final state (inspect the JSON report's `constraint_audit.violations`).
- `2`: Input error (missing `.brd`, invalid XML, or `RoutedCopperError`).

---

## 6. Key Concepts & Tuning Tips

### 6.1 Using `--proximity-group`
Global power and ground nets (`GND`, `VCC`, `3V3`, `VMOT`, etc.) are automatically down-weighted (`--pour-net-weight 0.05`) so power pours do not pull signal components off their optimal routing paths. However, components wired *only* to power and ground—such as **decoupling capacitors**—need an explicit hint to stay beside their target IC.

Pass one `--proximity-group` per functional cluster:
- **Decoupling caps:** `--proximity-group U1,C2,C3`
- **Crystal + load caps:** `--proximity-group U1,Y1,C12,C13`
- **Current-sense resistors:** `--proximity-group IC1,R1,R2`
- **USB differential series resistors:** `--proximity-group U3,R14,R15,J5`

Each group adds `2.0 * MST(group_centers)` to the objective, pulling those components together while still enforcing zero courtyard overlap.

### 6.2 Hard Constraints & Soft Overlap Legalization
- **Always enforced (never violated):**
  - Locked components (`locked="yes"`) never move or rotate.
  - Components stay on their original side (keep-side default).
  - Transformed courtyards stay inside the layer `20` board outline minus edge clearance.
- **Courtyards & Side Occupancy:**
  - Derived from package `tKeepout` (39) / `bKeepout` (40) if present, otherwise the union of `<pad>`, `<smd>`, `<hole>`, and `tPlace`/`bPlace` expanded by `--courtyard-margin-mm`.
  - SMD-only parts block only their mounted side (`top` or `bottom`); opposite-side SMDs may overlap in XY.
  - THT parts (any `<pad>` or `<hole>`) block **both** top and bottom sides.
- **Pre-Existing Overlaps:** If your initial board already has tight hand-placed courtyard or mounting-hole overlaps, `eagle6-placer` applies `--overlap-penalty` (`250.0` per violation) and rejects moves that increase overlap count, actively pushing components apart until violations reach `0`.

### 6.3 Reading the Preview Graphic
The `--preview` image displays **BEFORE** (left) and **AFTER** (right) with:
- **Slate boxes:** Locked components (`locked="yes"`)
- **Red boxes / pads:** Unlocked top-side components
- **Blue boxes / pads:** Unlocked bottom-side components
- **Green circles:** Through-hole (`<pad>`) pins
- **White / light-blue lines:** `tPlace` (21) / `bPlace` (22) silkscreen outlines (disable with `--hide-place`)
- **Yellow lines:** Pin-accurate Euclidean MST airwires for non-pour signal nets

---

## 7. Applying Results Safely in EAGLE v6.6.0

### Recommended Verification Pipeline
1. **Review the Preview & JSON Report:** Confirm wirelength/crossing improvements, `constraint_audit.passed == true`, and reasonable component positions.
2. **Staged Dry-Run (via sibling `eagle6-mcp`):**
   - Run `validate_edit_script` on your `.brd` with the generated `_placed.scr` content to execute it inside headless EAGLE v6.6.0 on an isolated copy and inspect `drc_delta`.
3. **Optional Autorouting Benchmark (via sibling `eagle6-freerouting`):**
   - Route the staged board to compare actual unrouted airwires, via count, and trace length.
4. **Apply in EAGLE GUI (with full Undo):**
   - Open your `.brd` in CadSoft EAGLE v6.6.0.
   - In the EAGLE command bar, run:
     ```text
     SCRIPT '/absolute/path/to/placer/my_board_placed.scr';
     ```
   - Inspect the updated board; press `Ctrl+Z` (Undo) at any time to revert cleanly.

---

## 8. Troubleshooting
- **`Error: Unlocked components have existing routed copper: ...`**
  - One or more unlocked components are connected to a non-pour signal net that already has `<wire>` or `<via>` copper. Rip up those traces in EAGLE first, or pass `--allow-routed` if you intend to re-route afterward.
- **Preview generates `.svg` but no `.png`:**
  - Install ImageMagick (`sudo apt install imagemagick`) so `convert` is on `PATH`, or open the `.svg` directly in any browser.
- **Too much component movement from your hand layout:**
  - Increase `--displacement-weight` (e.g., `--displacement-weight 0.5` or `1.0`) and/or reduce `--steps`.
- **Single-quoted names in `.scr` (`ROTATE =R0 'R1';`):**
  - Intentional! In CadSoft EAGLE v6.6.0, unquoted `R1` after `ROTATE =R0` is misinterpreted as a `1°` rotation angle instead of resistor `R1`. Single-quoting guarantees exact execution for all designators.
