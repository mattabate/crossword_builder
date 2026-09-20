import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from crossword_constructor.wordlist import WordIndex, load_word_set, load_wordlist, normalize_word

SCORED = "APPLE;50\nbanana;40\nCHERRY;10\nFIG;60\nice cream;45\nDON'T;30\nR2D2;50\n\nAPPLE;20\n"
PLAIN = "apple\nBanana\n\ncherry\nfig\n"
MIXED = "APPLE;50\nBANANA\nCHERRY;10\n"


class WordlistLoaderTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def _write(self, name, text):
        path = os.path.join(self._dir.name, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_scored_format(self):
        words = load_wordlist(self._write("scored.txt", SCORED))
        # uppercased, punctuation and spaces removed, R2D2 skipped, APPLE kept once
        self.assertEqual(words, ["APPLE", "BANANA", "CHERRY", "FIG", "ICECREAM", "DONT"])

    def test_plain_format(self):
        words = load_wordlist(self._write("plain.txt", PLAIN))
        self.assertEqual(words, ["APPLE", "BANANA", "CHERRY", "FIG"])

    def test_min_score(self):
        path = self._write("scored.txt", SCORED)
        self.assertEqual(load_wordlist(path, min_score=45), ["APPLE", "FIG", "ICECREAM"])
        self.assertEqual(load_wordlist(path, min_score=61), [])

    def test_min_score_keeps_unscored_words(self):
        path = self._write("mixed.txt", MIXED)
        self.assertEqual(load_wordlist(path, min_score=45), ["APPLE", "BANANA"])

    def test_length_bounds_and_exclude(self):
        path = self._write("scored.txt", SCORED)
        self.assertEqual(load_wordlist(path, min_length=4, max_length=5), ["APPLE", "DONT"])
        self.assertEqual(
            load_wordlist(path, max_length=6, exclude={"FIG"}), ["APPLE", "BANANA", "CHERRY", "DONT"]
        )

    def test_word_set(self):
        path = self._write("bad.txt", "fig\nAPPLE;50\n")
        self.assertEqual(load_word_set(path), {"FIG", "APPLE"})

    def test_normalize(self):
        self.assertEqual(normalize_word(" sour cream "), "SOURCREAM")
        self.assertIsNone(normalize_word("R2D2"))
        self.assertIsNone(normalize_word("   "))


class WordIndexTests(unittest.TestCase):
    def setUp(self):
        self.index = WordIndex(["CAT", "COT", "CUT", "DOG", "DOT", "COAT"])

    def test_pattern_lookup(self):
        self.assertEqual(sorted(self.index.candidates_for("C.T")), ["CAT", "COT", "CUT"])
        self.assertEqual(sorted(self.index.candidates_for(".O.")), ["COT", "DOG", "DOT"])
        self.assertEqual(sorted(self.index.candidates_for("...")), ["CAT", "COT", "CUT", "DOG", "DOT"])
        self.assertEqual(self.index.candidates_for("DOG"), ["DOG"])
        self.assertEqual(self.index.candidates_for("DIG"), [])
        self.assertEqual(self.index.candidates_for("Z.."), [])

    def test_length_without_words(self):
        self.assertEqual(self.index.candidates_for("....."), [])
        self.assertEqual(self.index.words_of_length(5), [])

    def test_membership_and_size(self):
        self.assertIn("COAT", self.index)
        self.assertNotIn("COATS", self.index)
        self.assertEqual(len(self.index), 6)
        self.assertEqual(self.index.lengths(), {3, 4})


if __name__ == "__main__":
    unittest.main()
