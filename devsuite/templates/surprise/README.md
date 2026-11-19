# Surprise

Randomize a material for inspiration. One button, one undo step.

Press Surprise (wheel, Style page, bottom row) and the selected object gets a fresh material: a random family, style, and layout, plus parameters within sane ranges. The pick is seeded, and the seed is stored, so the same seed always reproduces the same material.

Done when (from the PO8 spec):

- 10 Surprises produce at least 8 distinct materials.
- The same seed reproduces the same material.
- One undo step restores the previous material.

This is the suite's first template and its proving ground: the smallest add-on that runs the whole loop — chat, wheel button, render, test, pack. The pick logic (`pick_material`, `pick_parameters` in `src/shared/pick.py`) is finished and tested on its own. Applying the pick to a real object waits on the Reblend loader's plugin API (Phase 1).
