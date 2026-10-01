import csv
import io
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from import_csv import inspect


class TrackerTest(unittest.TestCase):
    def test_import_dry_run_classifies_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contacts.csv"
            path.write_text("name,kind,stage\nAda,buyer,Qualified\n,lead,New\n")
            good, bad = inspect(path)
            self.assertEqual(len(good), 1)
            self.assertEqual(bad, [3])


if __name__ == "__main__":
    unittest.main()
