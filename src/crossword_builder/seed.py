"""Place seed (theme) entries into a template to make starting grids.

A placement is ``ROW,COL,DIRECTION,WORD``. ROW and COL are 0-based and give
the first cell of the word. DIRECTION is ``across`` or ``down`` (``a`` and
``d`` also work). WORD may list alternatives separated by ``|``::

    3,1,across,BLUEBERRY
    5,1,across,SOURCREAM|SOURDOUGH

With alternatives, one starting grid is made for every combination that
fits. Combinations that clash, or that use the same word twice, are skipped.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import List, Tuple

from .grid import C_UNKNOWN, C_WALL, Direction, Grid, dims
from .wordlist import normalize_word


@dataclass(frozen=True)
class Placement:
    start: Tuple[int, int]  # (row, col), 0-based
    direction: Direction
    words: Tuple[str, ...]  # alternatives


def place_word(grid: Grid, start: Tuple[int, int], word: str, direction: Direction) -> Grid:
    """
    Write ``word`` into ``grid``, beginning at ``start`` and proceeding in
    ``direction`` (ACROSS = +col, DOWN = +row).

    Returns a copy of the grid with the word inserted. Raises ValueError if
    the word leaves the grid, hits a wall, or clashes with an existing
    letter.
    """
    height, width = dims(grid)
    new_rows = grid.copy()
    r0, c0 = start

    for k, ch in enumerate(word):
        r = r0 + k if direction == Direction.DOWN else r0
        c = c0 + k if direction == Direction.ACROSS else c0

        if not (0 <= r < height and 0 <= c < width):
            raise ValueError(f"Cannot place {word}: {(r, c)} is outside the {height}x{width} grid")

        cell = new_rows[r][c]
        if cell == C_WALL:
            raise ValueError(f"Cannot place {word}: wall at {(r, c)}")
        if cell != C_UNKNOWN and cell != ch:
            raise ValueError(
                f"Cannot place {word}: letter clash at {(r, c)}, grid has '{cell}', word needs '{ch}'"
            )

        new_rows[r] = f"{new_rows[r][:c]}{ch}{new_rows[r][c + 1:]}"

    return new_rows


def parse_placement(spec: str) -> Placement:
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 4:
        raise ValueError(f"bad placement {spec!r}: expected ROW,COL,DIRECTION,WORD")
    try:
        row, col = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"bad placement {spec!r}: ROW and COL must be integers") from None

    d = parts[2].lower()
    if d in ("a", "across"):
        direction = Direction.ACROSS
    elif d in ("d", "down"):
        direction = Direction.DOWN
    else:
        raise ValueError(f"bad placement {spec!r}: DIRECTION must be 'across' or 'down'")

    words = []
    for raw in parts[3].split("|"):
        word = normalize_word(raw)
        if word is None:
            raise ValueError(f"bad placement {spec!r}: {raw!r} is not a word")
        words.append(word)
    return Placement((row, col), direction, tuple(words))


def make_seed_grids(template: Grid, placements: List[Placement]) -> Tuple[List[Grid], List[str]]:
    """Return (grids, notes). ``notes`` explains every skipped combination."""
    grids: List[Grid] = []
    notes: List[str] = []
    for combo in itertools.product(*(p.words for p in placements)):
        if len(set(combo)) != len(combo):
            notes.append(f"skipped {' + '.join(combo)}: the same word is used twice")
            continue
        out = template.copy()
        try:
            for placement, word in zip(placements, combo):
                out = place_word(out, placement.start, word, placement.direction)
        except ValueError as e:
            notes.append(f"skipped {' + '.join(combo)}: {e}")
            continue
        if out not in grids:
            grids.append(out)
    return grids, notes
