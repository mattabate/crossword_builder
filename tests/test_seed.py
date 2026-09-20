import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from crossword_constructor.grid import Direction
from crossword_constructor.seed import make_seed_grids, parse_placement, place_word

# 3 rows x 5 columns
TEMPLATE = ["..█..", ".....", "█...█"]


class PlaceWordTests(unittest.TestCase):
    def test_across_and_down(self):
        grid = place_word(TEMPLATE, (1, 0), "HELLO", Direction.ACROSS)
        self.assertEqual(grid, ["..█..", "HELLO", "█...█"])
        grid = place_word(grid, (0, 1), "BEG", Direction.DOWN)
        self.assertEqual(grid, [".B█..", "HELLO", "█G..█"])
        self.assertEqual(TEMPLATE, ["..█..", ".....", "█...█"])  # input untouched

    def test_word_may_not_leave_the_grid(self):
        with self.assertRaises(ValueError) as cm:
            place_word(TEMPLATE, (1, 2), "HELLO", Direction.ACROSS)
        self.assertIn("outside", str(cm.exception))
        with self.assertRaises(ValueError):
            place_word(TEMPLATE, (1, 1), "HELLO", Direction.DOWN)

    def test_word_may_not_cross_a_wall(self):
        with self.assertRaises(ValueError) as cm:
            place_word(TEMPLATE, (0, 0), "HELLO", Direction.ACROSS)
        self.assertIn("wall", str(cm.exception))

    def test_letter_clash(self):
        grid = place_word(TEMPLATE, (1, 0), "HELLO", Direction.ACROSS)
        with self.assertRaises(ValueError) as cm:
            place_word(grid, (0, 1), "BAG", Direction.DOWN)
        self.assertIn("clash", str(cm.exception))


class SeedGridTests(unittest.TestCase):
    def test_parse_placement(self):
        p = parse_placement("1,0,across,hello|HALLO")
        self.assertEqual(p.start, (1, 0))
        self.assertEqual(p.direction, Direction.ACROSS)
        self.assertEqual(p.words, ("HELLO", "HALLO"))
        self.assertEqual(parse_placement("0,1,d,BEG").direction, Direction.DOWN)
        for bad in ("1,0,across", "x,0,across,HELLO", "1,0,sideways,HELLO", "1,0,a,R2D2"):
            with self.assertRaises(ValueError):
                parse_placement(bad)

    def test_alternatives_make_one_grid_per_combination_that_fits(self):
        placements = [parse_placement("1,0,a,HELLO|HALLO"), parse_placement("0,1,d,BEG|BAG")]
        grids, notes = make_seed_grids(TEMPLATE, placements)
        self.assertEqual(
            grids,
            [[".B█..", "HELLO", "█G..█"], [".B█..", "HALLO", "█G..█"]],
        )
        self.assertEqual(len(notes), 2)  # HELLO + BAG and HALLO + BEG clash


if __name__ == "__main__":
    unittest.main()
