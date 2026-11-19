"""The Blender drive (DOSSIER.md §8.3, Phase 5): drive Blender in
background mode, don't embed it.

Blender is a full program with its own window and its own Python —
it cannot live inside another program's window. So the suite drives
it the way SKULLPT already does: write a small test script, start
Blender as a subprocess (``blender --background --factory-startup
--python test_script.py``), and read the results back.

* ``runner`` — find Blender, run a test, collect checks, renders,
  and the log, and write the test run record (§9.4).
* ``scripts`` — generate the test script Blender runs (plain text,
  generatable without Blender present).

This package is stdlib only and headless. The Blender test window
is the next item; it calls this package from a worker thread.
"""
