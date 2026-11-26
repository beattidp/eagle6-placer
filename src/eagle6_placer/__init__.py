"""eagle6-placer: Auto-placement optimizer for CadSoft EAGLE v6.6.0 .brd files.

This package parses CadSoft EAGLE v6.6.0 XML board files read-only, optimizes
the positions and orientations of unlocked components (``locked != "yes"``) for
improved routability, and emits human-reviewable EAGLE ``.scr`` scripts plus
structured JSON metrics reports.
"""

__all__ = ["__version__"]
__version__ = "0.1.1"
