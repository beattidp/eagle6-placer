"""Unit and integration tests for the decoupled eagle6-placer MCP server."""

import asyncio
from pathlib import Path

from eagle6_placer.mcp_server import (
    audit_placement_board,
    create_mcp_server,
    optimize_board_placement,
)


def test_audit_placement_board(tangled_polish_brd: Path) -> None:
    """audit_placement_board returns dimensions, locked/unlocked lists, and initial metrics."""
    res = audit_placement_board(str(tangled_polish_brd))
    assert res["eagle_version"] == "6.6.0"
    assert res["outline_mm"]["width"] == 50.0
    assert res["outline_mm"]["height"] == 40.0
    assert res["components"]["locked_names"] == ["J1", "J2", "U1"]
    assert res["components"]["unlocked_count"] == 6
    assert res["routed_copper_guard"]["ready_without_allow_routed"] is True
    assert res["initial_audit"]["passed"] is True


def test_optimize_board_placement_polish_and_place(
    tmp_path: Path, tangled_polish_brd: Path, unplaced_fresh_brd: Path
) -> None:
    """Both polish and place MCP handlers emit .scr, preview, manifest, and inline script."""
    polish_dir = tmp_path / "polish"
    res_p = optimize_board_placement(
        str(tangled_polish_brd),
        mode="polish",
        output_dir=str(polish_dir),
        steps=600,
        seed=42,
        proximity_groups=[["U1", "C1"]],
        preview=True,
    )
    assert res_p["mode"] == "polish"
    assert res_p["constraint_audit"]["passed"] is True
    assert "GRID MM;" in res_p["script_content"]
    assert Path(res_p["script_path"]).is_file()
    assert Path(res_p["preview_svg_path"]).is_file()

    place_dir = tmp_path / "place"
    res_c = optimize_board_placement(
        str(unplaced_fresh_brd),
        mode="place",
        output_dir=str(place_dir),
        steps=600,
        seed=10,
        candidates=2,
        keep_all_candidates=True,
        preview=False,
    )
    assert res_c["mode"] == "place"
    assert res_c["constraint_audit"]["passed"] is True
    assert Path(res_c["manifest_path"]).is_file()
    assert len(res_c["candidates"]) == 2
    assert res_c["preview_svg_path"] is None


def test_create_mcp_server_registers_all_tools() -> None:
    """Verify MCPServer registers audit_placement, polish_board, and place_board."""
    server = create_mcp_server()
    tools = asyncio.run(server.list_tools())
    tool_names = {t.name for t in tools}
    assert {"audit_placement", "polish_board", "place_board"}.issubset(tool_names)
