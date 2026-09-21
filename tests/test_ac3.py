import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from crossword_builder.ac3 import ac3_reduce, fill_in_squares_one_possibility, initialise
from crossword_builder.wordlist import WordIndex


class AC3Tests(unittest.TestCase):
    """A 2x2 grid with the top left cell fixed to A.

        A.
        ..

    Words: AT, AS, AN, TO, SO.

    By hand:
    * Row 0 and column 0 both match "A.", so each starts as AT, AS or AN.
    * Cell (0, 1) is the second letter of row 0 (T, S or N) and the first
      letter of column 1 (A, T or S). The intersection is {S, T}.
    * Cell (1, 0) is {S, T} by the same argument.
    * Row 1 and column 1 must now start with S or T: only TO and SO are left.
    * Both end in O, so cell (1, 1) is {O}. AN is gone from row 0 and column 0.
    """

    WORDS = ["AT", "AS", "AN", "TO", "SO"]

    def test_narrows_constrained_cells(self):
        grid = ["A.", ".."]
        words, square_map = initialise(grid, WordIndex(self.WORDS))

        # before propagation an unknown cell allows every letter
        self.assertEqual(len(square_map[(0, 1)].possible_chars), 26)
        self.assertEqual(square_map[(0, 0)].possible_chars, {"A"})

        words, square_map = ac3_reduce(words, square_map)
        self.assertIsNotNone(words)
        self.assertEqual(square_map[(0, 0)].possible_chars, {"A"})
        self.assertEqual(square_map[(0, 1)].possible_chars, {"S", "T"})
        self.assertEqual(square_map[(1, 0)].possible_chars, {"S", "T"})
        self.assertEqual(square_map[(1, 1)].possible_chars, {"O"})

        by_slot = {(w.start, w.direction.name): sorted(w.possibilities) for w in words}
        self.assertEqual(by_slot[((0, 0), "ACROSS")], ["AS", "AT"])
        self.assertEqual(by_slot[((0, 0), "DOWN")], ["AS", "AT"])
        self.assertEqual(by_slot[((1, 0), "ACROSS")], ["SO", "TO"])
        self.assertEqual(by_slot[((0, 1), "DOWN")], ["SO", "TO"])

        # forced letters are written into a copy of the grid
        self.assertEqual(fill_in_squares_one_possibility(grid, square_map), ["A.", ".O"])
        self.assertEqual(grid, ["A.", ".."])

    def test_contradiction(self):
        # With only AT and AS, row 1 would have to start with T or S.
        words, square_map = initialise(["A.", ".."], WordIndex(["AT", "AS"]))
        self.assertEqual(ac3_reduce(words, square_map), (None, None))

    def test_fixed_entry_that_is_not_a_word(self):
        words, square_map = initialise(["AX", ".."], WordIndex(self.WORDS))
        self.assertEqual(ac3_reduce(words, square_map), (None, None))


if __name__ == "__main__":
    unittest.main()
