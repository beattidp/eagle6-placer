"""Unit tests for the Before/After SVG/PNG placement preview renderer."""

from pathlib import Path

from eagle6_placer.cli import main
from eagle6_placer.optimizer import LocalPolishOptimizer, PolishConfig
from eagle6_placer.parser import EagleBoardParser
from eagle6_placer.preview import PlacementPreviewRenderer, PreviewOptions


def test_preview_svg_shows_and_hides_tplace(tangled_polish_brd: Path) -> None:
    """tPlace/bPlace silkscreen is rendered by default and hidden with show_place=False."""
    board = EagleBoardParser().parse(tangled_polish_brd)
    result = LocalPolishOptimizer(
        board, PolishConfig(steps=300, grid_mm=0.5, seed=42)
    ).optimize()

    svg_with_place = PlacementPreviewRenderer(
        board, options=PreviewOptions(show_place=True)
    ).render_comparison_svg(result)
    svg_without_place = PlacementPreviewRenderer(
        board, options=PreviewOptions(show_place=False)
    ).render_comparison_svg(result)

    assert "tPlace/bPlace" in svg_with_place
    assert "tPlace/bPlace" not in svg_without_place
    assert svg_with_place.count("<line ") > svg_without_place.count("<line ")


def test_cli_preview_flag_writes_svg(
    tmp_path: Path, tangled_polish_brd: Path
) -> None:
    """CLI --preview flag emits <stem>_preview.svg alongside .scr and .json."""
    code = main(
        [
            "polish",
            str(tangled_polish_brd),
            "--output-dir",
            str(tmp_path),
            "--steps",
            "300",
            "--seed",
            "42",
            "--preview",
        ]
    )
    assert code == 0
    assert (tmp_path / "tangled_polish_preview.svg").is_file()
