"""Packing: manifest validation, secret scanning, emitters, install.

manifest.py and secrets_scan.py are the Phase 1 suite side (with
writer.py, the manifest writer). builder.py and installer.py are the
Reblend emitter — Phase 4, pulled forward while Phase 3 waits on the
Reblend loader. blender.py is the Blender emitter, Phase 4's other
half.
"""
