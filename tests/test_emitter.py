"""Unit tests for EAGLE v6 .scr script emission and JSON reporting."""

import json
from pathlib import Path

from eagle6_placer.emitter import EagleScriptEmitter
from eagle6_placer.optimizer import LocalPolishOptimizer, PolishConfig
from eagle6_placer.parser import EagleBoardParser


def test_emitter_writes_valid_scr_and_json(
    tmp_path: Path, tangled_polish_brd: Path
) -> None:
    """Emitted .scr must only touch unlocked parts and match EAGLE v6 syntax."""
    board = EagleBoardParser().parse(tangled_polish_brd)
    result = LocalPolishOptimizer(
        board, PolishConfig(steps=1500, grid_mm=0.5, seed=42)
    ).optimize()

    emitter = EagleScriptEmitter()
    script_path, report_path = emitter.write_outputs(
        board, result, output_dir=tmp_path
    )

    assert script_path.is_file()
    assert report_path.is_file()

    script_text = script_path.read_text(encoding="utf-8")
    assert "GRID MM;" in script_text
    assert "RATSNEST;" in script_text
    assert "GRID LAST;" in script_text

    # Locked components (J1, J2, U1) must NEVER appear in MOVE or ROTATE commands,
    # and all emitted component names must be single-quoted (regression check for
    # EAGLE v6 parsing unquoted R1/R2 as rotation angles).
    for line in script_text.splitlines():
        if line.startswith(("MOVE ", "ROTATE ")):
            assert "'" in line, f"Expected single-quoted element name in: {line}"
            for locked in ("J1", "J2", "U1"):
                assert f"'{locked}'" not in line

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["constraint_audit"]["passed"] is True
    assert report["component_counts"]["locked"] == 3
    assert report["component_counts"]["modified"] > 0
    assert report["metrics"]["after"]["total_cost"] < report["metrics"]["before"]["total_cost"]


def test_emitter_uses_mr_syntax_for_bottom_parts(
    tmp_path: Path, mixed_tht_keepout_brd: Path
) -> None:
    """Bottom-side rotations must emit ``ROTATE =MR<angle> '<name>';`` syntax."""
    board = EagleBoardParser().parse(mixed_tht_keepout_brd)
    result = LocalPolishOptimizer(
        board, PolishConfig(steps=2000, grid_mm=0.5, seed=7)
    ).optimize()

    emitter = EagleScriptEmitter()
    script_text = emitter.render_script(board, result)
    for line in script_text.splitlines():
        if line.startswith("ROTATE ") and (
            line.endswith(" 'R1';") or line.endswith(" 'R2';")
        ):
            assert "ROTATE =MR" in line


def test_emitter_emits_mirror_rotate_move_on_side_flip(
    mixed_tht_keepout_brd: Path,
) -> None:
    """When a component flips sides, emit MIRROR, ROTATE, and MOVE in sequence."""
    from eagle6_placer.geometry import ElementTransform
    from eagle6_placer.optimizer import OptimizationResult

    board = EagleBoardParser().parse(mixed_tht_keepout_brd)
    init_state = board.initial_state()
    best_state = init_state.copy()
    # Flip C1 from top (R180) to bottom (MR90) at (20, 20).
    best_state.poses["C1"] = ElementTransform(20.0, 20.0, 90.0, mirrored=True)

    dummy_cost = LocalPolishOptimizer(board, PolishConfig(steps=0)).optimize().initial_cost
    result = OptimizationResult(
        initial_state=init_state,
        best_state=best_state,
        initial_cost=dummy_cost,
        best_cost=dummy_cost,
        steps_executed=1,
        accepted_moves=1,
        feasible_proposals=1,
        rejected_infeasible=0,
        runtime_seconds=0.01,
        seed=42,
        final_violations=[],
    )
    script = EagleScriptEmitter().render_script(board, result)
    lines = [ln.strip() for ln in script.splitlines()]
    idx = lines.index("MIRROR 'C1';")
    assert lines[idx + 1] == "ROTATE =MR90 'C1';"
    assert lines[idx + 2] == "MOVE 'C1' (20.0000 20.0000);"
