import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from crossword_builder.ac3 import get_word_locations, initialise
from crossword_builder.grid import (
    C_UNKNOWN,
    C_WALL,
    Direction,
    TemplateError,
    dims,
    find_unchecked_cells,
    get_entries,
    get_words_in_grid,
    parse_template,
    parse_templates,
    str_to_grid,
    transpose,
    validate_grid,
)
from crossword_builder.wordlist import WordIndex


class TemplateParsingTests(unittest.TestCase):
    def test_native_characters(self):
        grid = parse_template("█..\n.A.\n..█\n")
        self.assertEqual(grid, ["█..", ".A.", "..█"])
        self.assertEqual(dims(grid), (3, 3))

    def test_alias_characters(self):
        # '#' is a wall, '@' is an unknown cell, lowercase letters are uppercased
        grid = parse_template("#.@\nab.\n")
        self.assertEqual(grid, [C_WALL + C_UNKNOWN + C_UNKNOWN, "AB" + C_UNKNOWN])

    def test_non_square_dimensions(self):
        grid = parse_template("....#\n.....\n#....\n")
        self.assertEqual(dims(grid), (3, 5))  # (height, width)
        self.assertEqual(dims(transpose(grid)), (5, 3))

    def test_surrounding_whitespace_and_blank_lines_are_ignored(self):
        grid = parse_template("\n\n  ...  \n  ...  \n\n")
        self.assertEqual(grid, ["...", "..."])

    def test_ragged_rows_are_rejected(self):
        with self.assertRaises(TemplateError) as cm:
            parse_template("....\n...\n....\n")
        message = str(cm.exception)
        self.assertIn("line 2", message)
        self.assertIn("same length", message)

    def test_unexpected_character_is_rejected(self):
        with self.assertRaises(TemplateError) as cm:
            parse_template("..\n.?\n")
        self.assertIn("line 2, column 2", str(cm.exception))

    def test_empty_template_is_rejected(self):
        with self.assertRaises(TemplateError):
            parse_template("\n\n")

    def test_several_grids_in_one_file(self):
        grids = parse_templates("..\n..\n\nAB\n..\n")
        self.assertEqual(grids, [["..", ".."], ["AB", ".."]])
        with self.assertRaises(TemplateError):
            parse_template("..\n..\n\nAB\n..\n")

    def test_str_to_grid(self):
        self.assertEqual(str_to_grid("ABCDEF", 3), ["ABC", "DEF"])
        self.assertEqual(str_to_grid("ABCDEF", 2), ["AB", "CD", "EF"])
        with self.assertRaises(ValueError):
            str_to_grid("ABCDE", 3)


class SlotExtractionTests(unittest.TestCase):
    """Slots on a 3 row x 5 column grid.

        AB#CD
        .....
        #...#
    """

    GRID = ["AB█CD", ".....", "█...█"]

    def setUp(self):
        self.index = WordIndex([])

    def test_across_slots(self):
        slots = get_word_locations(self.GRID, Direction.ACROSS, self.index)
        self.assertEqual(
            [(w.start, w.length) for w in slots],
            [((0, 0), 2), ((0, 3), 2), ((1, 0), 5), ((2, 1), 3)],
        )

    def test_down_slots(self):
        slots = get_word_locations(self.GRID, Direction.DOWN, self.index)
        self.assertEqual(
            [(w.start, w.length) for w in slots],
            [((0, 0), 2), ((0, 1), 3), ((0, 3), 3), ((0, 4), 2), ((1, 2), 2)],
        )

    def test_slots_end_at_the_grid_edges(self):
        # Row 1 is open up to the right edge and row 2 is open again one row
        # below. Each slot must stay inside its own row or column.
        for direction in (Direction.ACROSS, Direction.DOWN):
            for w in get_word_locations(self.GRID, direction, self.index):
                r, c = w.start
                if direction == Direction.ACROSS:
                    self.assertLessEqual(c + w.length, 5)
                else:
                    self.assertLessEqual(r + w.length, 3)

        open_grid = ["...", "..."]  # 2 rows x 3 columns, no walls
        across = get_word_locations(open_grid, Direction.ACROSS, self.index)
        down = get_word_locations(open_grid, Direction.DOWN, self.index)
        self.assertEqual([(w.start, w.length) for w in across], [((0, 0), 3), ((1, 0), 3)])
        self.assertEqual(
            [(w.start, w.length) for w in down], [((0, 0), 2), ((0, 1), 2), ((0, 2), 2)]
        )

    def test_square_map_links(self):
        words, square_map = initialise(self.GRID, self.index)
        self.assertEqual(len(words), 9)
        self.assertEqual(len(square_map), 12)  # 15 cells minus 3 walls
        # cell (1, 2): third cell of the 5 long across slot, first cell of a down slot
        across_id, across_pos = square_map[(1, 2)].across
        down_id, down_pos = square_map[(1, 2)].down
        self.assertEqual((words[across_id].start, across_pos), ((1, 0), 2))
        self.assertEqual((words[down_id].start, down_pos), ((1, 2), 0))
        # coordinates of the down slot in the last column
        last = [w for w in words if w.direction == Direction.DOWN and w.start == (0, 4)][0]
        self.assertEqual(last.coords, [(0, 4, 0), (1, 4, 1)])

    def test_entries_and_words(self):
        entries = get_entries(self.GRID)
        self.assertEqual(len(entries), 9)
        self.assertIn((0, 0, Direction.ACROSS, "AB"), entries)
        self.assertIn((0, 3, Direction.DOWN, "C.."), entries)
        # only completed runs count as words
        self.assertEqual(get_words_in_grid(self.GRID), ["AB", "CD"])

    def test_unchecked_cells_are_reported(self):
        validate_grid(self.GRID)  # fine
        # The cell (2, 2) has walls above it, so its down run is one cell long.
        bad = ["..█", "..█", "█.."]
        self.assertEqual(find_unchecked_cells(bad), [(2, 2)])
        with self.assertRaises(TemplateError):
            validate_grid(bad)


if __name__ == "__main__":
    unittest.main()
