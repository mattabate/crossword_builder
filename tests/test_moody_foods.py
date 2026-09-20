import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from crossword_constructor.ac3 import initialise
from crossword_constructor.filters import contains_bad_word_pairs
from crossword_constructor.grid import (
    C_UNKNOWN,
    C_WALL,
    Direction,
    dims,
    get_entries,
    get_words_in_grid,
    grid_contains_grid,
    is_complete,
    read_template,
    validate_grid,
)
from crossword_constructor.seed import make_seed_grids, parse_placement
from crossword_constructor.wordlist import WordIndex

EXAMPLE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "moody-foods"
)


class MoodyFoodsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = read_template(os.path.join(EXAMPLE, "template.txt"))
        cls.solution = read_template(os.path.join(EXAMPLE, "solution.txt"))

    def test_dimensions(self):
        self.assertEqual(dims(self.template), (9, 11))  # 9 rows, 11 columns
        self.assertEqual(dims(self.solution), (9, 11))

    def test_walls_match(self):
        for r in range(9):
            for c in range(11):
                self.assertEqual(
                    self.template[r][c] == C_WALL,
                    self.solution[r][c] == C_WALL,
                    f"wall mismatch at row {r}, column {c}",
                )

    def test_solution_is_complete_and_extends_the_template(self):
        self.assertTrue(is_complete(self.solution))
        self.assertFalse(is_complete(self.template))
        self.assertTrue(grid_contains_grid("".join(self.template), "".join(self.solution)))

    def test_theme_entries(self):
        across = {
            (r, c): text
            for r, c, direction, text in get_entries(self.solution)
            if direction == Direction.ACROSS
        }
        self.assertEqual(across[(3, 1)], "BLUEBERRY")
        self.assertEqual(across[(5, 1)], "SOURCREAM")
        fixed = [text for _, _, _, text in get_entries(self.template) if C_UNKNOWN not in text]
        self.assertEqual(sorted(fixed), ["BLUEBERRY", "SOURCREAM"])

    def test_template_is_usable(self):
        validate_grid(self.template)
        words, square_map = initialise(self.template, WordIndex([]))
        self.assertEqual(len(words), 16 + 16)  # 16 across entries, 16 down entries
        self.assertEqual(len(square_map), 99 - 15)  # 99 cells, 15 walls

    def test_solution_has_no_repeated_entry(self):
        words = get_words_in_grid(self.solution)
        self.assertEqual(len(words), 32)
        self.assertEqual(contains_bad_word_pairs(words), (False, None))

    def test_seed_command_rebuilds_the_template(self):
        blank = ["".join(ch if ch == C_WALL else C_UNKNOWN for ch in row) for row in self.template]
        placements = [
            parse_placement("3,1,across,BLUEBERRY"),
            parse_placement("5,1,a,sour cream"),
        ]
        grids, notes = make_seed_grids(blank, placements)
        self.assertEqual(grids, [self.template])
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
