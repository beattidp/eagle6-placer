

# eagle6-placer

 - Auto-placement optimizer for CadSoft EAGLE v6.6.0 XML board files (.brd).
 - optimizes the positions and orientations of unlocked components (locked != "yes") to improve routability
 - emits human-reviewable EAGLE .scr scripts.

It is designed as a decoupled sibling to [eagle6-mcp](https://github.com/beattidp/eagle6-mcp#readme/) (inspection, DRC, rendering, staged script validation) and [eagle6-freerouting](https://github.com/beattidp/eagle6-freerouting#readme) (autorouting), with zero code coupling between repositories.