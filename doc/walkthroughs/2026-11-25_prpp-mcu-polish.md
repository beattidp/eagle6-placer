# Walkthrough — `prpp-mcu.brd` Local Polish Benchmark (2026-11-25)

## Board Overview
- **Input:** `tests/fixtures/user-provided/prpp-mcu.brd` (read-only, untouched)
- **Dimensions:** `50.0 × 35.0 mm`, 2-layer `(1*16)`
- **Components:** 41 total — **7 locked** (`IC1`, `J1`, `J2`, `J3`, `J4`, `J5`, `X1`), **34 unlocked** (`C1`–`C13`, `R1`–`R15`, `SJ1`–`SJ3`, `U1`–`U3`).
- **Command:** `eagle6-placer polish tests/fixtures/user-provided/prpp-mcu.brd --allow-routed --steps 6000 --seed 42`

## Before vs. After Metrics
| Metric | Before | After | Delta |
| :--- | ---: | ---: | ---: |
| Weighted MST Wirelength | 513.21 mm | 487.44 mm | -25.77 mm (-5.0%) |
| Raw MST Wirelength | 765.90 mm | 723.81 mm | -42.09 mm (-5.5%) |
| Signal Airwire Crossings | 62 | 30 | -32 (-51.6%) |
| Total Objective Cost | 823.21 | 650.59 | -172.62 (-21.0%) |
| Courtyard/Hole Violations | 13 | 4 | -9 resolved |
| EAGLE v6.6.0 Staged DRC Errors | 1 | 1 | 0 new errors |
| EAGLE v6.6.0 Staged DRC Warnings | 97 | 96 | -1 warning |

## Key Findings
1. `U3` (FT230XS) rotated `R90 → R0`, aligning USB and UART pins directly between `J5` and `U1` and cutting signal airwire crossings in half (`62 → 30`).
2. `validate_edit_script` in real CadSoft EAGLE v6.6.0 confirmed `exit_code=0`, all 28 placement changes applied accurately (including bottom-side `SJ2` `MR90 → MR270` and `SJ3` `MR90 → MR0`), and 0 new DRC errors.
3. Three actionable Phase 1.1 refinements surfaced from this real board:
   - Penalize pre-existing courtyard overlaps so wedged parts (`C7`, `C8`, `R5`) are actively legalized.
   - Distinguish pour-net thermal/stitching vias (`GND`, `VMOT`) from routed signal traces in the routed-copper guard.
   - Support auto-detecting or specifying `--proximity-group` for decoupling caps.
