"""The measurements store (DOSSIER.md §6.10, §9.5, U37).

A tiny in-memory store of real numbers from the suite's own work:
how long the last build took, how big the last pack was, how long
the last Blender test ran and how many of its checks passed. The
measurements strip in the chat window reads from here and shows
the newest of each name, live.

What the store holds is always real: a measurement is recorded
only where the code genuinely produces the number (a build that
ran, a pack that was written, a test that finished). A failed
reply, a cancelled build, or a test that never produced a
checklist records nothing — a number that is not there is not
shown, and no placeholder ever stands in for one.

No persistence in v1: the store lives for the session, and a
restart starts empty. The strip says so plainly until the first
measurement lands.

The store is stdlib only and knows nothing about Qt. Windows that
want live updates subscribe a plain callable (``subscribe``): it
is called, with no arguments, after every successful record, so
the strip refreshes the moment a number lands. A subscriber that
fails never breaks a record — its failure is swallowed, and the
number still stands. Record from the UI thread: subscribers may
touch the UI.

Every function never raises: a bad record is ignored, with
nothing stored and no notification sent.
"""

from __future__ import annotations

import math

#: The newest measurement per name, in the order each name was
#: first recorded: {"name": {"name": ..., "value": ..., "unit": ...}}.
_MEASUREMENTS: dict[str, dict] = {}

#: Callables to run after a successful record, each taking no
#: arguments. A set, so subscribing the same callable twice is one
#: subscription.
_SUBSCRIBERS: set = set()


def record(name, value, unit) -> bool:
    """Store one measurement.

    ``name`` is the label ("Last build"), ``value`` a real number,
    ``unit`` its unit ("seconds", "KB", "of 5 checks"). A later
    record for the same name replaces the older one; the name keeps
    its place in the display order.

    Returns True when the measurement was stored, False when the
    input was bad — a name that is not a non-empty string, a value
    that is not a finite number, or a unit that is not a non-empty
    string. A bad record stores nothing and notifies nobody. Never
    raises.
    """
    if not isinstance(name, str) or not name.strip():
        return False
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if not math.isfinite(value):
        return False
    if not isinstance(unit, str) or not unit.strip():
        return False
    _MEASUREMENTS[str(name)] = {
        "name": str(name),
        "value": value,
        "unit": str(unit),
    }
    _notify()
    return True


def latest(name) -> dict | None:
    """The newest measurement for ``name``, or None when nothing
    has been recorded under it. The returned dict is a copy."""
    entry = _MEASUREMENTS.get(name)
    return dict(entry) if entry is not None else None


def all_latest() -> list[dict]:
    """The newest measurement for every name, in the order each
    name was first recorded. Copies, so a caller cannot rewrite
    the store by accident. Empty when nothing has been recorded."""
    return [dict(entry) for entry in _MEASUREMENTS.values()]


def clear() -> None:
    """Forget every measurement. Tests use this so each test starts
    from an empty store; the suite itself never clears mid-session."""
    _MEASUREMENTS.clear()


def subscribe(callback) -> None:
    """Run ``callback`` (no arguments) after every successful
    record. Subscribing the same callable twice is one
    subscription. A callback that is not callable is ignored."""
    if callable(callback):
        _SUBSCRIBERS.add(callback)


def unsubscribe(callback) -> None:
    """Stop running ``callback`` after records. Forgetting to
    unsubscribe keeps the callback alive, so windows unsubscribe
    when they close."""
    _SUBSCRIBERS.discard(callback)


def _notify() -> None:
    """Tell every subscriber a measurement landed. A subscriber
    that fails never breaks the record."""
    for callback in list(_SUBSCRIBERS):
        try:
            callback()
        except Exception:
            pass
