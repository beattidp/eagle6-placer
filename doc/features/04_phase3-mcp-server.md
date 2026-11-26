# 04 — Phase 3: Decoupled MCP Server (`eagle6-placer-mcp`)

## Overview
Phase 3 (`v0.3.0-phase3`) packages `eagle6-placer`'s read-only placement audit, local polish, coarse-to-fine placement, and Before/After preview capabilities as a standalone **Model Context Protocol (MCP)** stdio server (`eagle6-placer-mcp`).

Core CLI and library usage retains **zero external runtime dependencies**; the MCP SDK is declared as an optional extra (`pip install -e '.[mcp]'`), supporting both `mcp>=2.0` (`MCPServer`) and `mcp 1.x` (`FastMCP`).

## Registered MCP Tools (`src/eagle6_placer/mcp_server.py`)
1. **`audit_placement(brd_path, courtyard_margin_mm=0.25, edge_clearance_mm=None, ignore_pour_copper=True)`**
   - Read-only placement audit returning board outline dimensions, locked/unlocked component lists, routed-copper guard status, initial MST wirelength, airwire crossings, congestion penalty, and initial constraint violations.
2. **`polish_board(brd_path, ...)`**
   - Runs local polish Simulated Annealing (single or multi-seed via `candidates` / `keep_all_candidates`), supports `allow_mirror`, `allow_mirror_specs`, `restrict_mirror_specs`, `proximity_groups`, and `preview`/`hide_place`.
   - Returns structured before/after metrics, constraint audit, output paths (`script_path`, `report_path`, `manifest_path`, `preview_svg_path`, `preview_png_path`), and inline `script_content` ready to pass directly into `eagle6-mcp`'s `validate_edit_script`.
3. **`place_board(brd_path, ...)`**
   - Runs coarse-to-fine placement (`ForceDirectedPlacer` + `OverlapLegalizer` + SA) for fresh off-board or scattered boards with the same structured output contract.

## MCP Client Configuration Example
```json
{
  "mcpServers": {
    "eagle6-placer": {
      "command": "/home/beattidp/.pyenv/shims/eagle6-placer-mcp",
      "args": []
    }
  }
}
```

## Verification
- `pytest -v`: **43 passed** (including `tests/test_mcp_server.py` verifying `audit_placement_board`, `optimize_board_placement` in both `polish` and `place` modes, and `create_mcp_server()` tool registration via `list_tools()`).
- Console script `/home/beattidp/.pyenv/shims/eagle6-placer-mcp` verified on `PATH`.
