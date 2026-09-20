import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from crossword_constructor.filters import (
    contains_bad_word_pairs,
    contains_duplicate,
    load_bad_pairs,
    load_contains_words,
)
from crossword_constructor.grid import get_words_in_grid

GRID = ["█ORE", "AREA", "SCAR", "HAM█"]
# across: ORE AREA SCAR HAM, down: ASH ORCA REAM EAR


class FilterTests(unittest.TestCase):
    def test_words_of_the_grid(self):
        self.assertEqual(
            get_words_in_grid(GRID), ["ORE", "AREA", "SCAR", "HAM", "ASH", "ORCA", "REAM", "EAR"]
        )

    def test_clean_grid_passes(self):
        self.assertEqual(contains_bad_word_pairs(get_words_in_grid(GRID)), (False, None))

    def test_bad_pair_rejects_the_grid(self):
        bad_pairs = frozenset([frozenset(["HAM", "ORCA"])])
        rejected, message = contains_bad_word_pairs(get_words_in_grid(GRID), bad_pairs)
        self.assertTrue(rejected)
        self.assertIn("HAM", message)
        self.assertIn("ORCA", message)

    def test_unrelated_bad_pair_is_ignored(self):
        bad_pairs = frozenset([frozenset(["HAM", "EGGS"])])
        rejected, _ = contains_bad_word_pairs(get_words_in_grid(GRID), bad_pairs)
        self.assertFalse(rejected)

    def test_duplicate_rejects_the_grid(self):
        symmetric = ["█ARE", "AREA", "REST", "EAT█"]  # every across word is also a down word
        words = get_words_in_grid(symmetric)
        self.assertTrue(contains_duplicate(words))
        rejected, message = contains_bad_word_pairs(words)
        self.assertTrue(rejected)
        self.assertIn("Duplicate", message)

    def test_shared_contained_word_rejects_the_grid(self):
        contains = {"SCAR": ["CAR"], "ORCA": ["CAR"], "AREA": ["ARE"]}
        rejected, message = contains_bad_word_pairs(get_words_in_grid(GRID), frozenset(), contains)
        self.assertTrue(rejected)
        self.assertIn("CAR", message)

        rejected, _ = contains_bad_word_pairs(
            get_words_in_grid(GRID), frozenset(), {"SCAR": ["CAR"], "AREA": ["ARE"]}
        )
        self.assertFalse(rejected)

    def test_partial_grid_only_counts_completed_words(self):
        partial = ["█ORE", "AREA", "SC.R", "HA.█"]
        bad_pairs = frozenset([frozenset(["HAM", "ORCA"])])
        rejected, _ = contains_bad_word_pairs(get_words_in_grid(partial), bad_pairs)
        self.assertFalse(rejected)


class FilterFileTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def _write(self, text):
        path = os.path.join(self._dir.name, "f.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_load_bad_pairs(self):
        pairs = load_bad_pairs(self._write("ham orca\n\nEAST,WEST\nNorth; South\n"))
        self.assertEqual(
            pairs,
            frozenset(
                [
                    frozenset(["HAM", "ORCA"]),
                    frozenset(["EAST", "WEST"]),
                    frozenset(["NORTH", "SOUTH"]),
                ]
            ),
        )

    def test_bad_pairs_line_with_three_words_is_an_error(self):
        with self.assertRaises(ValueError) as cm:
            load_bad_pairs(self._write("HAM ORCA\nONE TWO THREE\n"))
        self.assertIn("line 2", str(cm.exception))

    def test_load_contains_words(self):
        contains = load_contains_words(self._write("SOURCREAM sour cream\nICECREAM ICE CREAM\n"))
        self.assertEqual(
            contains, {"SOURCREAM": ["SOUR", "CREAM"], "ICECREAM": ["ICE", "CREAM"]}
        )


if __name__ == "__main__":
    unittest.main()
