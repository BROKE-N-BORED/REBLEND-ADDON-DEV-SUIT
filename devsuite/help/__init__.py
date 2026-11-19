"""The How to Use index content (DOSSIER.md §6.10, U22).

The entries live here, as plain Python data — a list of dicts,
each with a title, a one-line summary, and plain-words body text.
Data, not code: the help window reads this list and shows it, and
nothing here can run. A plain module (rather than Markdown files
on disk) keeps the text next to the tests that check it: every
entry is asserted to carry no em-dash and no bare "&", and the
three journeys from §3 stay the first three entries.
"""

from devsuite.help.entries import ENTRIES, get_entries

__all__ = ["ENTRIES", "get_entries"]
