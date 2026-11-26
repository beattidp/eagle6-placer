"""Shared pytest fixtures for eagle6-placer unit and integration tests."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the synthetic EAGLE v6 .brd fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def tangled_polish_brd() -> Path:
    """Return path to the tangled local-polish benchmark .brd fixture."""
    return FIXTURES_DIR / "tangled_polish.brd"


@pytest.fixture
def mixed_tht_keepout_brd() -> Path:
    """Return path to the mixed THT/SMD + keepout + pour .brd fixture."""
    return FIXTURES_DIR / "mixed_tht_keepout.brd"
