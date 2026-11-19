"""The update check: silent on launch, ask-first, verified pull.

``check.py`` asks GitHub whether a newer Release is out (never
downloading anything); ``apply.py`` pulls a Release through the
verified path (checksum first, install second) and restarts the
suite. ``Updater`` is the one object the chat window holds: the
window takes one in its constructor, so tests pass a fake and
never touch the network or the real install.
"""

from __future__ import annotations

from devsuite.update.apply import (
    apply_update,
    default_applications_dir,
    default_install_dir,
    find_install,
    restart,
)
from devsuite.update.check import (
    REPO,
    check_for_update,
    current_version,
    is_newer,
    parse_version,
)

__all__ = [
    "REPO",
    "Updater",
    "apply_update",
    "check_for_update",
    "current_version",
    "default_applications_dir",
    "default_install_dir",
    "find_install",
    "is_newer",
    "parse_version",
    "restart",
]


class Updater:
    """The real updater for one installed suite: is it installed,
    is a newer release out, pull it, restart into it.

    ``install_dir`` / ``applications_dir`` default to the
    installer's defaults; ``api_url`` / ``urlopen`` are the test
    seams for a fake update server (the window never passes
    them). Every method is plain-words data, never a raise, so
    the window can run the check in a worker and report the
    result without ever crashing on a network problem.
    """

    def __init__(self, install_dir=None, applications_dir=None,
                 api_url=None, urlopen=None):
        self._install_dir = install_dir
        self._applications_dir = applications_dir
        self._api_url = api_url
        self._urlopen = urlopen

    def is_installed(self):
        """True when the suite is installed (the install record
        is there). A tree run with no install has nothing to
        update, so the window skips the check entirely."""
        return find_install(self._install_dir) is not None

    def current_version(self):
        """The running suite's version, or None when it cannot
        be told."""
        return current_version()

    def check(self):
        """The update check: the ``check_for_update`` result
        dict — state "newer", "current", or "unknown", with the
        release attached when there is one to pull."""
        return check_for_update(
            self.current_version(),
            urlopen=self._urlopen,
            api_url=self._api_url,
        )

    def apply(self, release, progress=None):
        """Pull ``release`` through the verified path and install
        it. Returns ``(ok, message)`` in plain words."""
        return apply_update(
            release,
            install_dir=self._install_dir,
            applications_dir=self._applications_dir,
            urlopen=self._urlopen,
            progress=progress,
        )

    def relaunch(self):
        """Start the suite again in the background, detached so
        it survives this process quitting. Returns ``(command,
        error)`` — the caller must check the error before
        quitting."""
        return restart(install_dir=self._install_dir)
