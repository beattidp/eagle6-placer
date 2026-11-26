# EAGLE v6 Auto-Placement Safety Rules

- Never directly mutate user `.brd` or `.sch` XML files on disk; doing so can break CadSoft EAGLE v6 forward/back-annotation.
- All placement changes must be emitted as human-reviewable EAGLE `.scr` scripts (with single-quoted component designators such as `ROTATE =R0 'R1';`, `MOVE 'R1' (x y);`, `MIRROR 'C1';`, `RATSNEST;`).
- Locked components (`locked="yes"`) are strictly immobile anchors and must never be moved, rotated, or mirrored.
- Always dry-run generated placement `.scr` scripts on a staged copy via `eagle6-mcp`'s `validate_edit_script` and check `run_drc` before instructing the user to run `SCRIPT '<path>';` in EAGLE GUI with full Undo support.
- Respect the routed-copper guard: do not force `--allow-routed` on unlocked components with routed signal traces unless the user explicitly intends to rip up and re-route those nets.
