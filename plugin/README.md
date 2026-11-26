# eagle6-placer Plugin

Antigravity plugin bundling the **`eagle6-placer-mcp`** server, placement safety rules, and end-to-end EAGLE v6 component auto-placement workflow skill.

## Included Tools (`eagle6-placer` MCP Server)
- `audit_placement` — Read-only board placement audit (dimensions, locked/unlocked parts, routed-copper guard, initial MST wirelength, crossings, congestion, and courtyard/hole violations).
- `polish_board` — Local polish Simulated Annealing with soft overlap legalization, optional `--allow-mirror` / `--restrict-mirror` range specs, proximity groups, multi-seed candidates, and Before/After SVG/PNG previews.
- `place_board` — Coarse-to-fine placement (force-directed + spiral overlap legalization + SA) for fresh off-board or scattered boards.

Designed to compose cleanly with sibling plugins `eagle6-mcp` and `eagle6-freerouting`.
