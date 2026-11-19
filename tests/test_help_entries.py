"""Tests for devsuite.help.entries — the How to Use index content.

Stdlib only: the entries are plain data, so their checks run on
system python too, not just the Qt venv.

The rules under test (DOSSIER.md §6.10, U22):

* Every entry has a non-empty title, summary, and body; titles
  are unique.
* The three journeys from §3 are the first three entries, in the
  dossier's order.
* No em-dash and no bare "&" anywhere in the visible text — the
  window shows these strings verbatim, and visible UI text carries
  neither.
"""

import unittest

from devsuite.help.entries import ENTRIES, get_entries


class HelpEntriesTest(unittest.TestCase):
    def test_every_entry_is_well_formed(self):
        self.assertGreater(len(ENTRIES), 0)
        for entry in ENTRIES:
            for field in ("title", "summary", "body"):
                self.assertIn(field, entry)
                self.assertTrue(
                    entry[field].strip(),
                    f"{entry.get('title', '?')} has an empty {field}",
                )

    def test_titles_are_unique(self):
        titles = [entry["title"] for entry in ENTRIES]
        self.assertEqual(len(titles), len(set(titles)))

    def test_the_three_journeys_come_first(self):
        titles = [entry["title"] for entry in ENTRIES[:3]]
        self.assertTrue(titles[0].startswith("Journey A:"))
        self.assertTrue(titles[1].startswith("Journey B:"))
        self.assertTrue(titles[2].startswith("Journey C:"))

    def test_no_em_dash_or_bare_ampersand(self):
        for entry in ENTRIES:
            for field in ("title", "summary", "body"):
                text = entry[field]
                self.assertNotIn(
                    "—", text,
                    f"{entry['title']} {field} carries an em-dash",
                )
                self.assertNotIn(
                    "&", text,
                    f"{entry['title']} {field} carries a bare &",
                )

    def test_get_entries_returns_copies(self):
        entries = get_entries()
        entries[0]["title"] = "rewritten"
        self.assertNotEqual(ENTRIES[0]["title"], "rewritten")


if __name__ == "__main__":
    unittest.main()
