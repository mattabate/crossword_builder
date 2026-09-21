"""Configuration and per-process context for the search.

``BuilderConfig`` is plain data. It can be pickled and sent to worker
processes. ``BuilderContext`` is built from a config inside each process. It
holds the word index and the pattern cache, which are large and are rebuilt
per process instead of being pickled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Tuple

from .wordlist import WordIndex


@dataclass(frozen=True)
class BuilderConfig:
    # The wordlist, already filtered and uppercased.
    words: Tuple[str, ...]
    # Pairs of words that must not appear in the same grid.
    bad_pairs: FrozenSet[FrozenSet[str]] = frozenset()
    # answer -> words it contains. Two answers that contain the same word
    # must not appear in the same grid.
    contains: Dict[str, List[str]] = field(default_factory=dict)
    # Use the 3x3 block pruning expansion (slower per grid, prunes more).
    block_pruning: bool = True
    # A 3x3 block is pruned when MIN < (sum of candidate letters over its 9 cells) < MAX.
    min_block_sum: int = 35
    max_block_sum: int = 90
    # A slot of a block is pruned when 1 < (number of distinct 3-letter segments) < this.
    max_segments: int = 100
    # Run the duplicate / bad pair filters on a grid that was completed by the
    # last branching letter, before saving it as a solution. The original
    # script did not. Set to False to reproduce that.
    validate_solutions: bool = True
    # Print a line for every grid rejected by the duplicate / bad pair filters.
    verbose: bool = False


class BuilderContext:
    def __init__(self, config: BuilderConfig):
        self.config = config
        self.index = WordIndex(config.words)
        self.bad_pairs = config.bad_pairs
        self.contains = config.contains
