"""Full fills of a tiny grid with a handwritten wordlist.

Template (4x4, two corner walls), with a name for every open cell:

    #...        # a b c
    ....        d e f g
    ....        h i j k
    ...#        l m n #

Across entries: abc, defg, hijk, lmn. Down entries: dhl, aeim, bfjn, cgk.

Wordlist (tests/data/tiny_wordlist.txt):

    3 letters: ORE HAD HAM ASH EAR ASK EAT OAR ARE SAD PAD
    4 letters: AREA SCAR ORCA READ REAM REAL STAR ORAL REST OPEN

Hand enumeration. The down entry dhl starts with the first letters of rows 1
and 2, so those two letters must begin a 3 letter word: OR, HA, AS, EA, OA,
AR, SA or PA. No 4 letter word starts with H, E or P. The down entry cgk ends
with the last letters of rows 1 and 2, which must end a 3 letter word: RE, AD,
AM, SH, AR, SK or AT. That leaves these (row 1, row 2) pairs:

* ORCA + READ: aeim is .RE. = AREA, bfjn is .CA. = SCAR, cgk is .AD. Row 0
  is A S ? = ASH, so cgk = HAD. Row 3 is E A R = EAR.      -> fill 3
* ORCA + REAM: the same, with cgk = HAM.                    -> fill 4
* ORCA + REST: bfjn would be .CS. and no word fits.
* AREA + SCAR: aeim is .RC. = ORCA, bfjn is .EA. = READ, REAM or REAL, cgk
  is .AR = EAR or OAR, dhl is ASH or ASK. Row 0 is O R ? = ORE, so cgk = EAR.
  Row 3 is (H or K) A (D, M or L) = HAD or HAM.             -> fills 1 and 2
* AREA + STAR: aeim would be .RT. and no word fits.
* AREA + READ or REAM: row 0 would be A R (H, S or P), not a word.
* AREA + REST: gives ARE / AREA / REST / EAT, where every across word is
  also a down word. The duplicate filter rejects it.
* SCAR or STAR + AREA, and ORCA, ORAL or OPEN + AREA: cgk would end in RA,
  AA, LA or NA and no word fits.

So there are exactly four fills. Fills 3 and 4 are the transposes of 1 and 2.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from crossword_constructor.context import ConstructorConfig, ConstructorContext
from crossword_constructor.grid import parse_template
from crossword_constructor.pruning import super_get_new_grids
from crossword_constructor.runner import RunOptions, run_search
from crossword_constructor.search import cell_heuristic, get_new_grids
from crossword_constructor.wordlist import load_wordlist

WORDLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tiny_wordlist.txt")

TEMPLATE = "#...\n....\n....\n...#\n"

FILL_1 = ("█ORE", "AREA", "SCAR", "HAD█")
FILL_2 = ("█ORE", "AREA", "SCAR", "HAM█")
FILL_3 = ("█ASH", "ORCA", "READ", "EAR█")
FILL_4 = ("█ASH", "ORCA", "REAM", "EAR█")
ALL_FILLS = {FILL_1, FILL_2, FILL_3, FILL_4}


def _fill(config, **options):
    options.setdefault("workers", 1)
    options.setdefault("quiet", True)
    result = run_search([parse_template(TEMPLATE)], config, RunOptions(**options))
    return result, {tuple(g) for g in result.solutions}


class TinyFillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.words = tuple(load_wordlist(WORDLIST))

    def test_wordlist_size(self):
        self.assertEqual(len(self.words), 21)

    def test_default_search_finds_exactly_the_four_fills(self):
        result, fills = _fill(ConstructorConfig(words=self.words))
        self.assertEqual(fills, ALL_FILLS)
        self.assertEqual(len(result.solutions), 4)  # no fill is reported twice
        self.assertTrue(result.exhausted)
        self.assertFalse(result.interrupted)

    def test_block_pruning_forced_on(self):
        # The grid is so constrained that the default lower threshold skips
        # its two open 3x3 blocks. Drop the threshold so they are pruned.
        result, fills = _fill(ConstructorConfig(words=self.words, min_block_sum=0))
        self.assertEqual(fills, ALL_FILLS)
        self.assertEqual(len(result.solutions), 4)

    def test_plain_search_without_block_pruning(self):
        result, fills = _fill(ConstructorConfig(words=self.words, block_pruning=False))
        self.assertEqual(fills, ALL_FILLS)
        self.assertEqual(len(result.solutions), 4)

    def test_small_batches_and_plateau_mode_find_the_same_fills(self):
        _, fills = _fill(ConstructorConfig(words=self.words), chunk_size=1, seed=7)
        self.assertEqual(fills, ALL_FILLS)
        _, fills = _fill(ConstructorConfig(words=self.words), chunk_size=2, plateau=True, buffer=1)
        self.assertEqual(fills, ALL_FILLS)

    def test_bad_pair_removes_the_fills_that_contain_it(self):
        bad_pairs = frozenset([frozenset(["HAM", "ORCA"])])
        for block_pruning in (True, False):
            config = ConstructorConfig(
                words=self.words, bad_pairs=bad_pairs, block_pruning=block_pruning
            )
            _, fills = _fill(config)
            self.assertEqual(fills, {FILL_1, FILL_3})

    def test_contained_words_filter(self):
        # SCAR and ORCA are in all four fills. Declare that both contain the
        # same word, and every fill must be rejected.
        contains = {"SCAR": ["CAR"], "ORCA": ["CAR"]}
        _, fills = _fill(ConstructorConfig(words=self.words, contains=contains))
        self.assertEqual(fills, set())

    def test_every_child_extends_its_parent(self):
        ctx = ConstructorContext(ConstructorConfig(words=self.words))
        start = parse_template(TEMPLATE)
        for step in (super_get_new_grids, get_new_grids):
            children = step(start, ctx, cell_heuristic)
            self.assertTrue(children)
            for child in children:
                self.assertEqual(len(child), 4)
                for parent_row, child_row in zip(start, child):
                    self.assertEqual(len(child_row), 4)
                    for p, c in zip(parent_row, child_row):
                        self.assertTrue(p == "." or p == c)
            # the children differ from each other
            self.assertEqual(len({tuple(c) for c in children}), len(children))

    def test_unfillable_template(self):
        result, fills = _fill(ConstructorConfig(words=("ORE", "AREA")))
        self.assertEqual(fills, set())
        self.assertTrue(result.exhausted)

    def test_max_solutions_stops_early(self):
        result, fills = _fill(ConstructorConfig(words=self.words), chunk_size=1, max_solutions=1)
        self.assertGreaterEqual(len(fills), 1)
        self.assertTrue(fills <= ALL_FILLS)

    def test_state_file_and_resume(self):
        with tempfile.TemporaryDirectory() as out:
            config = ConstructorConfig(words=self.words)
            first, _ = _fill(config, out_dir=out, chunk_size=1, max_solutions=1)
            state_path = os.path.join(out, "combined.json")
            self.assertEqual(first.state_path, state_path)
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
            self.assertEqual((state["height"], state["width"]), (4, 4))
            self.assertGreaterEqual(len(state["solutions"]), 1)

            # a second run refuses to overwrite unless told to
            with self.assertRaises(FileExistsError):
                _fill(config, out_dir=out)

            _fill(config, out_dir=out, resume=True)
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
            self.assertEqual(set(state["solutions"]), {"".join(f) for f in ALL_FILLS})
            self.assertEqual(state["snapshot"], {})

            with open(os.path.join(out, "solutions.txt"), encoding="utf-8") as f:
                blocks = [b for b in f.read().split("\n\n") if b.strip()]
            self.assertEqual({tuple(b.split("\n")) for b in blocks}, ALL_FILLS)

    def test_two_worker_processes(self):
        # Starts a real pool of two spawned worker processes.
        result, fills = _fill(ConstructorConfig(words=self.words), workers=2, chunk_size=2)
        self.assertEqual(fills, ALL_FILLS)
        self.assertEqual(len(result.solutions), 4)


if __name__ == "__main__":
    unittest.main()
