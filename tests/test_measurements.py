"""Tests for devsuite.measure.measurements — the measurements store.

Stdlib only: the store knows nothing about Qt. Run from the
project root:

    python3 -m unittest tests.test_measurements

The rules under test (DOSSIER.md §6.10, §9.5, U37):

* The store keeps the newest measurement per name, in the order
  each name was first recorded.
* A bad record is ignored: nothing stored, nobody notified, and
  the call never raises.
* Subscribers hear about a successful record, and only a
  successful one; unsubscribing stops the calls.
"""

import math
import unittest

from devsuite.measure.measurements import (
    all_latest,
    clear,
    latest,
    record,
    subscribe,
    unsubscribe,
)


class MeasurementsTest(unittest.TestCase):
    def setUp(self):
        clear()

    def tearDown(self):
        clear()

    def test_empty_store_reads_empty(self):
        self.assertIsNone(latest("Last build"))
        self.assertEqual(all_latest(), [])

    def test_record_and_latest(self):
        self.assertTrue(record("Last build", 2.3, "seconds"))
        entry = latest("Last build")
        self.assertEqual(entry["name"], "Last build")
        self.assertEqual(entry["value"], 2.3)
        self.assertEqual(entry["unit"], "seconds")

    def test_newest_wins_for_a_name(self):
        record("Last build", 2.3, "seconds")
        record("Last build", 4.1, "seconds")
        self.assertEqual(latest("Last build")["value"], 4.1)
        self.assertEqual(len(all_latest()), 1)

    def test_all_latest_keeps_first_record_order(self):
        record("Last build", 2.3, "seconds")
        record("Last pack size", 12.4, "KB")
        record("Last build", 4.1, "seconds")
        names = [entry["name"] for entry in all_latest()]
        self.assertEqual(names, ["Last build", "Last pack size"])

    def test_latest_returns_a_copy(self):
        record("Last build", 2.3, "seconds")
        entry = latest("Last build")
        entry["value"] = 99
        self.assertEqual(latest("Last build")["value"], 2.3)

    def test_bad_name_is_ignored(self):
        for bad in ("", "   ", 123, None):
            self.assertFalse(record(bad, 1.0, "seconds"))
        self.assertEqual(all_latest(), [])

    def test_bad_value_is_ignored(self):
        for bad in ("2.3", None, True, float("nan"), float("inf")):
            self.assertFalse(record("Last build", bad, "seconds"))
        self.assertEqual(all_latest(), [])

    def test_bad_unit_is_ignored(self):
        for bad in ("", "   ", 123, None):
            self.assertFalse(record("Last build", 1.0, bad))
        self.assertEqual(all_latest(), [])

    def test_int_values_are_numbers_too(self):
        self.assertTrue(record("Last Blender checks", 5, "of 5 checks"))
        self.assertEqual(latest("Last Blender checks")["value"], 5)

    def test_clear_empties_the_store(self):
        record("Last build", 2.3, "seconds")
        clear()
        self.assertEqual(all_latest(), [])
        self.assertIsNone(latest("Last build"))

    def test_subscriber_hears_a_record(self):
        heard = []

        def listen():
            heard.append(True)

        subscribe(listen)
        try:
            record("Last build", 2.3, "seconds")
            self.assertEqual(heard, [True])
        finally:
            unsubscribe(listen)

    def test_subscriber_ignores_a_bad_record(self):
        heard = []

        def listen():
            heard.append(True)

        subscribe(listen)
        try:
            record("Last build", "not a number", "seconds")
            self.assertEqual(heard, [])
        finally:
            unsubscribe(listen)

    def test_unsubscribe_stops_the_calls(self):
        heard = []

        def listen():
            heard.append(True)

        subscribe(listen)
        unsubscribe(listen)
        record("Last build", 2.3, "seconds")
        self.assertEqual(heard, [])

    def test_a_failing_subscriber_never_breaks_a_record(self):
        def broken():
            raise RuntimeError("the subscriber is broken")

        subscribe(broken)
        try:
            self.assertTrue(record("Last build", 2.3, "seconds"))
            self.assertEqual(latest("Last build")["value"], 2.3)
        finally:
            unsubscribe(broken)

    def test_subscribing_twice_is_one_subscription(self):
        heard = []

        def listen():
            heard.append(True)

        subscribe(listen)
        subscribe(listen)
        try:
            record("Last build", 2.3, "seconds")
            self.assertEqual(heard, [True])
        finally:
            unsubscribe(listen)


if __name__ == "__main__":
    unittest.main()
