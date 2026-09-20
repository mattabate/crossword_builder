"""Grid representation, template parsing and small grid helpers.

A grid is a list of row strings. Every row has the same length. The height
is ``len(grid)`` and the width is ``len(grid[0])``. Nothing in this package
assumes a square grid or a fixed size.

Cell characters used internally:

* ``█``  wall (black square)
* ``.``  unknown cell, still to be filled
* ``A`` to ``Z``  a fixed letter

Template files may also use ``#`` for a wall and ``@`` for an unknown cell.
Lowercase letters are uppercased.
"""
from __future__ import annotations

from enum import Enum
from typing import Iterator, List, Tuple

Grid = List[str]

C_WALL = "█"
C_UNKNOWN = "."
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

_WALL_CHARS = {C_WALL, "#"}
_UNKNOWN_CHARS = {C_UNKNOWN, "@"}


class Direction(Enum):
    ACROSS = 1
    DOWN = 2


class TemplateError(ValueError):
    """Raised when a template or grid file cannot be used."""


# ───────────────────────────── parsing ────────────────────────────────────────
def _parse_block(lines: List[Tuple[int, str]]) -> Grid:
    """Turn (line number, text) pairs into one validated grid."""
    rows: Grid = []
    first_line_no, first_text = lines[0]
    width = len(first_text)
    for line_no, text in lines:
        if len(text) != width:
            raise TemplateError(
                f"line {line_no} has {len(text)} cells but line {first_line_no} "
                f"has {width}. Every row of a grid must have the same length."
            )
        out = []
        for col, ch in enumerate(text):
            if ch in _WALL_CHARS:
                out.append(C_WALL)
            elif ch in _UNKNOWN_CHARS:
                out.append(C_UNKNOWN)
            elif ch.upper() in LETTERS and len(ch.upper()) == 1:
                out.append(ch.upper())
            else:
                raise TemplateError(
                    f"line {line_no}, column {col + 1}: unexpected character {ch!r}. "
                    f"Use '{C_WALL}' or '#' for a wall, '.' for an unknown cell, "
                    f"and A-Z for fixed letters."
                )
        rows.append("".join(out))
    return rows


def parse_templates(text: str) -> List[Grid]:
    """Parse one or more grids from text. Grids are separated by blank lines."""
    text = text.lstrip("﻿")
    grids: List[Grid] = []
    block: List[Tuple[int, str]] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            if block:
                grids.append(_parse_block(block))
                block = []
            continue
        block.append((line_no, line))
    if block:
        grids.append(_parse_block(block))
    if not grids:
        raise TemplateError("the template is empty")
    return grids


def parse_template(text: str) -> Grid:
    """Parse exactly one grid from text."""
    grids = parse_templates(text)
    if len(grids) != 1:
        raise TemplateError(
            f"expected one grid but found {len(grids)} (grids are separated by blank lines)"
        )
    return grids[0]


def read_templates(path: str) -> List[Grid]:
    with open(path, "r", encoding="utf-8") as f:
        return parse_templates(f.read())


def read_template(path: str) -> Grid:
    with open(path, "r", encoding="utf-8") as f:
        return parse_template(f.read())


# ───────────────────────────── helpers ────────────────────────────────────────
def dims(grid: Grid) -> Tuple[int, int]:
    """Return (height, width)."""
    return len(grid), len(grid[0])


def transpose(grid: Grid) -> Grid:
    """Swap rows and columns. A height x width grid becomes width x height."""
    return ["".join(row) for row in zip(*grid)]


def replace_char_in_grid(grid: Grid, loc: Tuple[int, int], c: str) -> Grid:
    """Return a copy of the grid with the cell at (row, col) set to ``c``."""
    out = grid.copy()
    row = out[loc[0]]
    out[loc[0]] = f"{row[:loc[1]]}{c}{row[loc[1] + 1:]}"
    return out


def grid_to_str(grid: Grid) -> str:
    """Flatten a grid into one string, row after row."""
    return "".join(grid)


def str_to_grid(grid_str: str, width: int) -> Grid:
    """Split a flat grid string into rows of ``width`` characters."""
    if width <= 0 or len(grid_str) % width != 0:
        raise ValueError(
            f"a grid string of length {len(grid_str)} cannot be split into rows of width {width}"
        )
    return [grid_str[i : i + width] for i in range(0, len(grid_str), width)]


def format_grid(grid: Grid) -> str:
    return "\n".join(grid)


def is_complete(grid: Grid) -> bool:
    return C_UNKNOWN not in "".join(grid)


def grid_contains_grid(template: str, grid: str) -> bool:
    """True if the flat ``grid`` agrees with the flat ``template`` on every non-unknown cell."""
    return all(tc == C_UNKNOWN or tc == gc for tc, gc in zip(template, grid))


def get_words_in_grid(grid: Grid) -> List[str]:
    """All completed runs in the grid, across first and then down.

    A run is a maximal stretch of cells between walls or edges. Runs that
    still contain an unknown cell are skipped.
    """
    across_words: List[str] = []
    for line in grid:
        across_words += [w for w in line.split(C_WALL) if w and C_UNKNOWN not in w]

    down_words: List[str] = []
    for line in transpose(grid):
        down_words += [w for w in line.split(C_WALL) if w and C_UNKNOWN not in w]

    return across_words + down_words


def iter_runs(grid: Grid) -> Iterator[Tuple[int, int, Direction, int]]:
    """Yield (row, col, direction, length) for every run of open cells, any length."""
    height, width = dims(grid)
    for r in range(height):
        c = 0
        while c < width:
            if grid[r][c] == C_WALL:
                c += 1
                continue
            start = c
            while c < width and grid[r][c] != C_WALL:
                c += 1
            yield (r, start, Direction.ACROSS, c - start)
    for c in range(width):
        r = 0
        while r < height:
            if grid[r][c] == C_WALL:
                r += 1
                continue
            start = r
            while r < height and grid[r][c] != C_WALL:
                r += 1
            yield (start, c, Direction.DOWN, r - start)


def get_entries(grid: Grid) -> List[Tuple[int, int, Direction, str]]:
    """Every entry (run of two or more cells) as (row, col, direction, text)."""
    out = []
    for r, c, direction, length in iter_runs(grid):
        if length < 2:
            continue
        if direction == Direction.ACROSS:
            text = grid[r][c : c + length]
        else:
            text = "".join(grid[r + i][c] for i in range(length))
        out.append((r, c, direction, text))
    return out


def find_unchecked_cells(grid: Grid) -> List[Tuple[int, int]]:
    """Open cells that are not part of both an across entry and a down entry.

    The search needs every open cell to sit in an across entry and a down
    entry of two or more cells.
    """
    in_across = set()
    in_down = set()
    for r, c, direction, length in iter_runs(grid):
        if length < 2:
            continue
        for i in range(length):
            if direction == Direction.ACROSS:
                in_across.add((r, c + i))
            else:
                in_down.add((r + i, c))
    height, width = dims(grid)
    return [
        (r, c)
        for r in range(height)
        for c in range(width)
        if grid[r][c] != C_WALL and ((r, c) not in in_across or (r, c) not in in_down)
    ]


def validate_grid(grid: Grid) -> None:
    """Raise TemplateError if the search cannot work on this grid."""
    bad = find_unchecked_cells(grid)
    if bad:
        shown = ", ".join(f"(row {r + 1}, column {c + 1})" for r, c in bad[:5])
        more = f" and {len(bad) - 5} more" if len(bad) > 5 else ""
        raise TemplateError(
            "every open cell must be part of an across entry and a down entry "
            f"of at least two cells. Unchecked cells: {shown}{more}."
        )
