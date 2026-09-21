"""One search step: take a partial grid and return its child grids.

``get_new_grids`` is the plain expansion:

1. build slots and cells, run AC-3
2. write every forced letter into the grid
3. reject the grid if its completed words contain a duplicate or a bad pair
4. pick one cell to branch on
5. return one child grid per candidate letter of that cell

The expansion with 3x3 block pruning lives in ``pruning.py``.
"""
from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Tuple

from .ac3 import SquareMap, Word, ac3_reduce, fill_in_squares_one_possibility, initialise
from .context import BuilderContext
from .filters import contains_bad_word_pairs
from .grid import C_UNKNOWN, Grid, get_words_in_grid, replace_char_in_grid

Heuristic = Callable[[int, int, Iterable[str]], tuple]


def cell_heuristic(x: int, y: int, chars) -> tuple:
    """Sort key for choosing the cell to branch on. The smallest key wins.

    The first component is 0 when both the row index and the column index
    are even, and 1 otherwise. The second component is the number of
    candidate letters. So cells on the even/even lattice are preferred, and
    among those the cell with the fewest candidates. Ties go to the first
    cell in row-major order.
    """
    return (
        (x % 2) + (y % 2) - (x % 2) * (y % 2),
        len(chars),
    )


def get_graph_of_open_cells(
    grid: Grid, square_map: SquareMap, words: List[Word]
) -> Tuple[List[Tuple[int, int]], List[int]]:
    """Build a graph over the unfilled cells.

    Nodes are cell indices (``width * row + col``). An unfilled cell is
    linked to the next undecided cell to its right in the same entry and to
    the next undecided cell below it in the same entry. A cell that is the
    only unfilled cell of both its entries is returned separately as a
    disconnected node.
    """
    height = len(grid)
    width = len(grid[0])
    connections: List[Tuple[int, int]] = []
    disconnected_nodes: List[int] = []

    for s, v in square_map.items():
        if grid[s[0]][s[1]] != C_UNKNOWN:
            continue

        index = width * s[0] + s[1]

        # The two words this cell belongs to
        aw = words[v.across[0]]
        dw = words[v.down[0]]

        ax, ay = aw.start
        across_word = grid[ax][ay : ay + aw.length]

        dx, dy = dw.start
        down_word = "".join(grid[dx + i][dy] for i in range(dw.length))

        if across_word.count(C_UNKNOWN) == 1 and down_word.count(C_UNKNOWN) == 1:
            # s is the only unfilled cell in both of its entries
            disconnected_nodes.append(index)
            continue

        # Walk right to the next undecided cell in the same row
        distance = 1
        while True:
            next_col = s[1] + distance
            if next_col >= width:  # hit the edge
                break
            location_to_check = (s[0], next_col)
            if location_to_check not in square_map:  # hit a wall
                break
            if len(square_map[location_to_check].possible_chars) > 1:
                connections.append((index, width * s[0] + next_col))
                break
            distance += 1

        # Walk down to the next undecided cell in the same column
        distance = 1
        while True:
            next_row = s[0] + distance
            if next_row >= height:  # hit the edge
                break
            location_to_check = (next_row, s[1])
            if location_to_check not in square_map:  # hit a wall
                break
            if len(square_map[location_to_check].possible_chars) > 1:
                connections.append((index, width * next_row + s[1]))
                break
            distance += 1

    return connections, disconnected_nodes


def find_acyclic_nodes(edge_list: List[Tuple[int, int]]) -> List[int]:
    """Nodes that belong to a connected component without a cycle (union-find)."""
    all_nodes = set()
    for u, v in edge_list:
        all_nodes.add(u)
        all_nodes.add(v)
    all_nodes = list(all_nodes)

    parent = {}
    rank = {}
    component_has_cycle = {}

    for node in all_nodes:
        parent[node] = node
        rank[node] = 0
        component_has_cycle[node] = False

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        root_x = find(x)
        root_y = find(y)

        if root_x == root_y:
            component_has_cycle[root_x] = True
            return

        if rank[root_x] < rank[root_y]:
            parent[root_x] = root_y
            component_has_cycle[root_y] |= component_has_cycle[root_x]
        elif rank[root_x] > rank[root_y]:
            parent[root_y] = root_x
            component_has_cycle[root_x] |= component_has_cycle[root_y]
        else:
            parent[root_y] = root_x
            rank[root_x] += 1
            component_has_cycle[root_x] |= (
                component_has_cycle[root_y] or component_has_cycle[root_x]
            )

    for u, v in edge_list:
        union(u, v)

    acyclic_nodes = []
    for node in all_nodes:
        root_node = find(node)
        if not component_has_cycle[root_node]:
            acyclic_nodes.append(node)

    acyclic_nodes.sort()
    return acyclic_nodes


def _pick_branch_square(
    square_map: SquareMap, width: int, skip: set, heuristic: Heuristic
) -> Optional[Tuple[int, int]]:
    branch_sq = None
    best_key = None
    for (x, y), sq in square_map.items():
        if len(sq.possible_chars) == 1:
            continue
        if width * x + y in skip:
            continue
        k = heuristic(x, y, sq.possible_chars)
        if best_key is None or k < best_key:
            best_key, branch_sq = k, (x, y)
    return branch_sq


def get_new_grids(
    grid: Grid, ctx: BuilderContext, heuristic: Heuristic = cell_heuristic
) -> List[Grid]:
    # ── AC-3 pass ────────────────────────────────────────────────────────────
    words, square_map = initialise(grid, ctx.index)
    words, square_map = ac3_reduce(words, square_map)
    if words is None:  # contradiction
        return []

    filled = fill_in_squares_one_possibility(grid, square_map)

    # ── global duplicate / bad-pair guards ───────────────────────────────────
    words_in_grid = get_words_in_grid(filled)
    has_bad_pair, error_msg = contains_bad_word_pairs(
        words_in_grid, ctx.bad_pairs, ctx.contains
    )
    if has_bad_pair:
        if error_msg and ctx.config.verbose:
            print(f"Rejected grid: {error_msg}")
        return []

    # ── choose branch square ─────────────────────────────────────────────────
    # Cells in a cycle-free component of the open-cell graph, and cells that
    # are the last open cell of both their entries, are skipped: they are
    # cheap to finish later, so branching goes to the tangled cells first.
    width = len(filled[0])
    connections, disconnected = get_graph_of_open_cells(filled, square_map, words)
    skippable = set(find_acyclic_nodes(connections) + disconnected)

    branch_sq = _pick_branch_square(square_map, width, skippable, heuristic)

    if branch_sq is None:
        # NOTE (differs from the original script): the original returned
        # ``filled`` here even when skipped cells were still undecided. The
        # driver then put that same grid back in the queue forever. Once only
        # skipped cells remain, branch on them with the same heuristic.
        branch_sq = _pick_branch_square(square_map, width, set(), heuristic)

    # ── fully forced ⇒ solution ──────────────────────────────────────────────
    if branch_sq is None:
        return [filled]

    # ── forward-check each letter before emitting child ──────────────────────
    x, y = branch_sq
    aw, ai = square_map[(x, y)].across  # across-word id & local index
    dw, di = square_map[(x, y)].down  # down-word id & local index

    across_poss = words[aw].possibilities
    down_poss = words[dw].possibilities

    children: List[Grid] = []
    for ch in sorted(square_map[(x, y)].possible_chars):
        # Letter must appear in some remaining word in both directions
        if not any(w[ai] == ch for w in across_poss):
            continue
        if not any(w[di] == ch for w in down_poss):
            continue
        children.append(replace_char_in_grid(filled, branch_sq, ch))

    return children
