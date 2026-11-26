# Phase 3 Implementation Plan — `eagle6-placer-mcp` (Decoupled MCP Server)

*Date: 2026-11-25*
*Baseline: `v0.2.0-phase2` (40 passing tests; local polish, coarse-to-fine `place`, 2D congestion, `--allow-mirror`/`--restrict-mirror`, multi-seed `--candidates`, `--preview`).*

---

## Goals & Exit Criteria
Phase 3 exposes `eagle6-placer`'s placement audit, local polish, coarse-to-fine placement, and preview capabilities as a standalone **Model Context Protocol (MCP)** stdio server (`eagle6-placer-mcp`) while keeping:
- **Zero external runtime dependencies** for core `eagle6-placer` CLI/library (`mcp>=1.0` lives in `[project.optional-dependencies] mcp`).
- **Zero code coupling** with `eagle6-mcp` and `eagle6-freerouting`.
- **Full safety invariants:** Read-only `.brd` access, `.scr`-only output (returned both on disk and inline as `script_content` for direct handoff to `eagle6-mcp`'s `validate_edit_script`), sacred locked parts, and routed-copper guard.

## MCP Tool Surface (`src/eagle6_placer/mcp_server.py`)
1. **`audit_placement`** — Read-only board placement audit returning board dimensions, locked/unlocked component names, routed-copper guard status, initial cost breakdown (MST wirelength, crossings, congestion), and any pre-existing courtyard/hole/keepout violations.
2. **`polish_board`** — Runs local polish SA (single or multi-seed), writes `.scr`, `.json`, optional `candidates_manifest.json`, and optional Before/After `_preview.svg`/`.png`, returning structured before/after metrics, audit status, output paths, and `script_content`.
3. **`place_board`** — Runs coarse-to-fine placement (`ForceDirectedPlacer` + `OverlapLegalizer` + SA) for fresh off-board or scattered boards, returning the same structured payload.

## Packaging & Verification
- Entry point: `eagle6-placer-mcp = "eagle6_placer.mcp_server:main"` in `pyproject.toml`.
- Compatible with both `mcp>=2.0` (`MCPServer`) and `mcp 1.x` (`FastMCP`).
- Verified via `pytest -v` (`tests/test_mcp_server.py`) testing both pure handler functions and `create_mcp_server()` tool registration/execution.
