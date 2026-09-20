"""Word slots, cell domains and AC-3 constraint propagation.

Each entry in the grid is a ``Word`` slot with a shrinking list of candidate
words. Each open cell is a ``Square`` with a shrinking set of candidate
letters. ``ac3_reduce`` alternates between the two until nothing changes:

* a word keeps only the candidates whose letters are allowed by its cells
* a cell keeps only the letters offered by both its across and its down word
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

from .grid import C_UNKNOWN, C_WALL, LETTERS, Direction, Grid, TemplateError, transpose
from .wordlist import WordIndex

Coord = Tuple[int, int]


class Word:
    """Dynamic word slot (candidates shrink while searching)."""

    __slots__ = ("start", "direction", "length", "possibilities", "coords")

    def __init__(
        self,
        start: Coord,
        direction: Direction,
        length: int,
        index: WordIndex,
        temp: str = "",
    ):
        self.start = start
        self.direction = direction
        self.length = length
        self.possibilities: List[str] = (
            index.words_of_length(length)  # no pattern: copy whole list
            if not temp
            else index.candidates_for(temp)
        )
        self.coords: List[Tuple[int, int, int]] = []  # (row, col, idx-in-word)


class Square:
    __slots__ = ("across", "down", "possible_chars")

    def __init__(self):
        self.across: Optional[Tuple[int, int]] = None  # (word-id, idx-in-word)
        self.down: Optional[Tuple[int, int]] = None
        self.possible_chars: set = set(LETTERS)


SquareMap = Dict[Coord, Square]


def get_word_locations(grid: Grid, direction: Direction, index: WordIndex) -> List[Word]:
    """Find all word slots in one direction. Words stop at walls and at the edges."""
    if direction == Direction.DOWN:
        grid = transpose(grid)

    # After the transpose a "row" is a column of the original grid.
    num_rows = len(grid)
    row_length = len(grid[0])

    out: List[Word] = []
    for rc in range(num_rows):
        row = grid[rc]
        start = -1

        for j in range(row_length):
            c = row[j]

            if c == C_WALL:
                # Hit a wall: if we were building a word, finalize it
                if start != -1 and (j - start) >= 2:  # minimum word length is 2
                    point = (rc, start) if direction == Direction.ACROSS else (start, rc)
                    out.append(Word(point, direction, j - start, index, temp=row[start:j]))
                start = -1
            else:
                # Not a wall: if not in a word, start one
                if start == -1:
                    start = j

        # End of row: finalize word if we were building one
        if start != -1 and (row_length - start) >= 2:
            point = (rc, start) if direction == Direction.ACROSS else (start, rc)
            out.append(
                Word(point, direction, row_length - start, index, temp=row[start:row_length])
            )

    if direction == Direction.DOWN:
        out.sort(key=lambda w: (w.start[0], w.start[1]))
    return out


def initialise(grid: Grid, index: WordIndex) -> Tuple[List[Word], SquareMap]:
    """Build word slots and the square map for constraint propagation."""
    height = len(grid)
    width = len(grid[0])
    square_map: SquareMap = {}

    # Create square objects for all non-wall cells
    for i in range(height):
        for j in range(width):
            letter = grid[i][j]
            if letter == C_WALL:
                continue
            sq = square_map.setdefault((i, j), Square())
            if letter != C_UNKNOWN:
                sq.possible_chars = {letter}

    words = get_word_locations(grid, Direction.ACROSS, index) + get_word_locations(
        grid, Direction.DOWN, index
    )

    # Link squares and words, and precompute coordinate lists
    for wid, w in enumerate(words):
        x, y = w.start
        for idx in range(w.length):
            xy = (
                (x, y + idx)  # ACROSS: same row, advance column
                if w.direction == Direction.ACROSS
                else (x + idx, y)  # DOWN: advance row, same column
            )
            w.coords.append((xy[0], xy[1], idx))
            if w.direction == Direction.ACROSS:
                square_map[xy].across = (wid, idx)
            else:
                square_map[xy].down = (wid, idx)

    for (i, j), sq in square_map.items():
        if sq.across is None or sq.down is None:
            raise TemplateError(
                f"the cell at row {i + 1}, column {j + 1} is not part of both an across "
                "entry and a down entry of at least two cells"
            )

    return words, square_map


def ac3_reduce(
    words: List[Word], square_map: SquareMap
) -> Tuple[Optional[List[Word]], Optional[SquareMap]]:
    """Propagate constraints until stable. Returns (None, None) on a contradiction."""
    square_version: Dict[Coord, int] = {xy: 0 for xy in square_map}
    word_seen: List[List[int]] = [[0] * len(w.coords) for w in words]

    def tighten_square(xy: Coord) -> Optional[bool]:
        sq = square_map[xy]
        aw, ai = sq.across
        dw, di = sq.down

        acc_set = {w[ai] for w in words[aw].possibilities}
        down_set = {w[di] for w in words[dw].possibilities}
        new_chars = acc_set & down_set

        if not new_chars:
            return False
        if new_chars != sq.possible_chars:
            sq.possible_chars = new_chars
            square_version[xy] += 1
            return True
        return None

    q_words = deque(range(len(words)))
    q_squares = deque(square_map.keys())

    enqueued_words = set(q_words)
    enqueued_squares = set(q_squares)

    while q_words or q_squares:
        # ---- tighten words -------------------------------------------
        while q_words:
            wid = q_words.popleft()
            enqueued_words.discard(wid)
            w = words[wid]
            seen = word_seen[wid]

            changed = False
            for i, (x, y, _) in enumerate(w.coords):
                if square_version[(x, y)] != seen[i]:
                    changed = True
                    break
            if not changed:
                continue

            allowed = [square_map[(x, y)].possible_chars for x, y, _ in w.coords]

            new_poss = []
            for cand in w.possibilities:
                for i in range(w.length):
                    if cand[i] not in allowed[i]:
                        break
                else:
                    new_poss.append(cand)

            if not new_poss:
                return None, None

            if len(new_poss) != len(w.possibilities):
                w.possibilities = new_poss
                for x, y, _ in w.coords:
                    if (x, y) not in enqueued_squares:
                        q_squares.append((x, y))
                        enqueued_squares.add((x, y))

            for i, (x, y, _) in enumerate(w.coords):
                seen[i] = square_version[(x, y)]

        # ---- tighten squares -----------------------------------------
        while q_squares:
            xy = q_squares.popleft()
            enqueued_squares.discard(xy)
            status = tighten_square(xy)
            if status is False:
                return None, None
            if status:
                sq = square_map[xy]
                for wid in (sq.across[0], sq.down[0]):
                    if wid not in enqueued_words:
                        q_words.append(wid)
                        enqueued_words.add(wid)

    return words, square_map


def fill_in_squares_one_possibility(grid: Grid, square_map: SquareMap) -> Grid:
    """Return a copy of the grid with every single-candidate cell written in."""
    g = grid.copy()
    for (x, y), sq in square_map.items():
        if len(sq.possible_chars) == 1:
            c = next(iter(sq.possible_chars))
            row = g[x]
            g[x] = row[:y] + c + row[y + 1 :]
    return g
