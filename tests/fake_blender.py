#!/usr/bin/env python3
"""A stand-in for Blender, for the drive's tests only (not shipped).

It mimics Blender's command-line contract: it accepts
``--background --factory-startup --python <script>``, prints
Blender-like lines, and behaves per the FAKE_BLENDER_MODE
environment variable:

* ``pass`` — prints a check line for every standard check (all
  passed) and writes a fake render file to DEVSUITE_OUT_DIR,
  exit 0.
* ``fail`` — prints a traceback and one failed check line, exit 1.
* ``crash`` — prints a fatal line and exits without reporting any
  check, exit 1.
* ``sleep`` — sleeps 60 seconds, so the runner's timeout fires.

It never runs the ``--python`` script it is handed: it only mimics
Blender's outer behaviour (arguments, output, exit code, files).
The generated test script itself is verified by parsing it (see
test_blender_drive.py), not by running it here.
"""

import json
import os
import struct
import sys
import time
import zlib


def tiny_png():
    """A valid 1x1 transparent PNG, built with zlib — so the test
    window's render preview genuinely loads it. Built, not
    transcribed: a hand-copied byte string turned out corrupt
    (bad CRC, short image data) and libpng refused it."""
    def chunk(typ, data):
        out = struct.pack(">I", len(data)) + typ + data
        return out + struct.pack(
            ">I", zlib.crc32(typ + data) & 0xFFFFFFFF
        )
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
    png += chunk(b"IEND", b"")
    return png


def check_line(name, passed, detail=""):
    return "DEVSUITE-CHECK " + json.dumps({
        "name": name,
        "passed": passed,
        "detail": detail,
    })


def main():
    args = sys.argv[1:]
    if "--python" not in args:
        print("fake_blender: no --python script given", file=sys.stderr)
        return 2
    print("Blender 5.3.0 (hash 000000000000)")
    print("Read blend: <startup>")
    mode = os.environ.get("FAKE_BLENDER_MODE", "pass")
    out_dir = os.environ.get("DEVSUITE_OUT_DIR", "")
    if mode == "pass":
        for name in (
            "Loads without errors",
            "Does not crash on the empty scene",
            "Operator runs",
            "Render is written",
            "Unloads clean",
        ):
            print(check_line(name, True, "ok."))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            with open(
                os.path.join(out_dir, "render-test.png"), "wb"
            ) as handle:
                handle.write(tiny_png())
        print("Blender quit")
        return 0
    if mode == "fail":
        print(check_line(
            "Loads without errors", False,
            "the add-on installed but is not enabled.",
        ))
        print(check_line(
            "Does not crash on the empty scene", False,
            "could not run — the add-on did not install.",
        ))
        print("Traceback (most recent call last):", file=sys.stderr)
        print(
            '  File "<string>", line 1, in <module>',
            file=sys.stderr,
        )
        print(
            "RuntimeError: the add-on installed but is not enabled.",
            file=sys.stderr,
        )
        return 1
    if mode == "crash":
        print("Error: EXCEPTION_ACCESS_VIOLATION", file=sys.stderr)
        print("Blender quit", file=sys.stderr)
        return 1
    if mode == "sleep":
        time.sleep(60)
        return 0
    print(f"fake_blender: unknown mode {mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
