# AGENTS.md — `eagle6-placer`

## Project Overview
`eagle6-placer` is a standalone Linux component auto-placement optimizer for **CadSoft EAGLE v6.6.0** XML board files (`.brd`). It optimizes the positions and orientations of **unlocked** components (`locked != "yes"`) to improve routability and emits human-reviewable EAGLE `.scr` scripts.

It is designed as a decoupled sibling to `eagle6-mcp` (inspection, DRC, rendering, staged script validation) and `eagle6-freerouting` (autorouting), with zero code coupling between repositories.

## Core Safety Invariants
1. **Read-Only `.brd` Access:** Never directly mutate user `.brd` or `.sch` XML files on disk. Direct XML mutation risks breaking CadSoft EAGLE v6 forward/back-annotation.
2. **Script-First Output:** All placement changes must be emitted as human-reviewable EAGLE `.scr` scripts (`GRID MM;`, `ROTATE`, `MOVE`, `MIRROR` when enabled, `RATSNEST;`, `GRID LAST;`) so the user can review and execute them in EAGLE GUI with full Undo support.
3. **Locked Parts Are Sacred:** Elements with `locked="yes"` must never be moved, rotated, or mirrored under any circumstance.
4. **Staged Verification:** Before recommending GUI execution of a generated `.scr` script on a real board, dry-run it on a staged copy via `eagle6-mcp` (`validate_edit_script`, `run_drc`, `render_board`).
5. **Routed Copper Guard:** Warn and refuse by default if unlocked components have existing routed `<wire>` or `<via>` copper unless the user explicitly opts in (`--allow-routed`).

## Platform & Development Conventions
- **OS:** Linux.
- **Python Environment:** Managed via `pyenv` virtualenv named `eagle6-placer` (see `.python-version`). Keep `requirements.txt` updated with `>=` constraints.
- **Repository Layout:**
  - `src/eagle6_placer/`: Modular, object-oriented Python package with comprehensive docstrings and engineering rationale comments.
  - `tests/`: `pytest` unit and regression tests, plus synthetic EAGLE v6 `.brd` fixtures in `tests/fixtures/`.
  - `doc/`: Design specifications (`doc/specification.md`), dated plans (`doc/plans/YYYY-MM-DD_*.md`), numbered feature docs (`doc/features/01_*.md`), dated walkthroughs (`doc/walkthroughs/YYYY-MM-DD_*.md`), and dated worklogs (`doc/worklogs/YYYY-MM-DD_*.md`).
- **Rule:** Never place source code or design-specific documentation in the project root directory.

## Session State Stack
- `STATE.md` in the project root tracks the current goal, completed work, blockers, exact next step, and active files.
- At session start, follow `.agents/skills/resume-session/SKILL.md`.
- At session end, follow `.agents/skills/session-handoff/SKILL.md`.
