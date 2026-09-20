"""Search step with 3x3 block pruning.

After AC-3, every fully open 3x3 block of cells is inspected. Three across
slots and three down slots pass through a block. Each slot contributes the
set of distinct 3-letter segments its remaining candidates place inside the
block. A segment survives only if the block can be completed around it:
there must be a choice of three crossing segments that reproduces it and
whose other rows (or columns) are also available segments. Candidates whose
segment did not survive are dropped, and AC-3 runs again.

This is stronger than AC-3, which only looks at one cell at a time. It is
also slower, so it is only applied to blocks and slots that are already
fairly constrained (see the thresholds in ``ConstructorConfig``).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .ac3 import SquareMap, Word, ac3_reduce, fill_in_squares_one_possibility, initialise
from .context import ConstructorContext
from .filters import contains_bad_word_pairs, contains_duplicate
from .grid import Grid, get_words_in_grid
from .search import Heuristic, cell_heuristic


def choose_branch_square(square_map: SquareMap, heuristic: Heuristic) -> Optional[Tuple[int, int]]:
    best = None
    best_key = None
    for (x, y), sq in square_map.items():
        if len(sq.possible_chars) <= 1:
            continue
        k = heuristic(x, y, sq.possible_chars)
        if best_key is None or k < best_key:
            best_key, best = k, (x, y)
    return best


def init_3x3_block(block: Tuple[int, int], words: List[Word], square_map: SquareMap) -> Dict:
    """
    For a 3x3 block with upper-left corner (x, y), returns
      {'across': [row0, row1, row2], 'down': [col0, col1, col2]}
    Each row / col entry is
      {'word_id': ..., 'pos': (x, y), 'slice_idx': k, 'segments': [unique 3-letter substrings]}
    """
    x, y = block
    out: Dict[str, List[Dict]] = {"across": [], "down": []}

    # three across rows
    for dx in (0, 1, 2):
        xi = x + dx
        wid, k = square_map[(xi, y)].across  # k = offset in word
        seg_set = {cand[k : k + 3] for cand in words[wid].possibilities}
        out["across"].append(
            {"word_id": wid, "pos": (xi, y), "slice_idx": k, "segments": list(seg_set)}
        )

    # three down columns
    for dy in (0, 1, 2):
        yj = y + dy
        wid, k = square_map[(x, yj)].down
        seg_set = {cand[k : k + 3] for cand in words[wid].possibilities}
        out["down"].append(
            {"word_id": wid, "pos": (x, yj), "slice_idx": k, "segments": list(seg_set)}
        )

    return out


def prune_single_word(init_data: Dict, orientation: str, widx: int) -> List[str]:
    """
    Prune one slot's segments: keep a 3-letter segment only if it can be
    embedded in at least one valid triple of crossing segments.
    orientation: 'across' or 'down'
    widx: index of the slot within that list, 0..2
    Returns the pruned segment list for that slot.
    """
    across = init_data["across"]
    down = init_data["down"]

    if orientation == "down":
        target_segs = down[widx]["segments"]
        other0, other1, other2 = (
            across[0]["segments"],
            across[1]["segments"],
            across[2]["segments"],
        )
        k = widx  # column position within each across segment
        pruned = []
        down_sets = [set(col["segments"]) for col in down]

        for seg in target_segs:
            ok = False
            for s0 in other0:
                for s1 in other1:
                    for s2 in other2:
                        # does this triple yield seg at column k?
                        if (s0[k] + s1[k] + s2[k]) != seg:
                            continue
                        # and do all three columns match some down segment?
                        c0 = s0[0] + s1[0] + s2[0]
                        c1 = s0[1] + s1[1] + s2[1]
                        c2 = s0[2] + s1[2] + s2[2]
                        if c0 in down_sets[0] and c1 in down_sets[1] and c2 in down_sets[2]:
                            ok = True
                            break
                    if ok:
                        break
                if ok:
                    break
            if ok:
                pruned.append(seg)

        return pruned

    # orientation == 'across'
    target_segs = across[widx]["segments"]
    other0, other1, other2 = (
        down[0]["segments"],
        down[1]["segments"],
        down[2]["segments"],
    )
    k = widx
    pruned = []
    across_sets = [set(row["segments"]) for row in across]

    for seg in target_segs:
        ok = False
        for d0 in other0:
            for d1 in other1:
                for d2 in other2:
                    # does this triple yield seg at row k?
                    if (d0[k] + d1[k] + d2[k]) != seg:
                        continue
                    # and do all three rows match some across segment?
                    r0 = d0[0] + d1[0] + d2[0]
                    r1 = d0[1] + d1[1] + d2[1]
                    r2 = d0[2] + d1[2] + d2[2]
                    if r0 in across_sets[0] and r1 in across_sets[1] and r2 in across_sets[2]:
                        ok = True
                        break
                if ok:
                    break
            if ok:
                break
        if ok:
            pruned.append(seg)
    return pruned


def super_get_new_grids(
    grid: Grid, ctx: ConstructorContext, heuristic: Heuristic = cell_heuristic
) -> List[Grid]:
    cfg = ctx.config
    height = len(grid)
    width = len(grid[0])

    words, square_map = initialise(grid, ctx.index)
    words, square_map = ac3_reduce(words, square_map)
    if words is None:
        return []

    # 1) find all fully open 3x3 blocks (must fit within the grid)
    offsets = [(dx, dy) for dx in (0, 1, 2) for dy in (0, 1, 2)]
    blocks = [
        (x, y)
        for (x, y) in square_map
        if x <= height - 3
        and y <= width - 3
        and all((x + dx, y + dy) in square_map for dx, dy in offsets)
    ]

    # 2) keep blocks whose total number of candidate letters is in range
    few = [
        (x, y)
        for (x, y) in blocks
        if cfg.min_block_sum
        < sum(len(square_map[(x + dx, y + dy)].possible_chars) for dx, dy in offsets)
        < cfg.max_block_sum
    ]

    # 3) process every such block
    for block in few:
        init_data = init_3x3_block(block, words, square_map)

        # gather every slot with few segments (but more than one, so still ambiguous)
        to_prune = []
        for idx, info in enumerate(init_data["across"]):
            if 1 < len(info["segments"]) < cfg.max_segments:
                to_prune.append(("across", idx))
        for idx, info in enumerate(init_data["down"]):
            if 1 < len(info["segments"]) < cfg.max_segments:
                to_prune.append(("down", idx))

        for orientation, local_idx in to_prune:
            entry = init_data[orientation][local_idx]
            wid = entry["word_id"]
            slice_idx = entry["slice_idx"]

            before = len(entry["segments"])
            pruned = prune_single_word(init_data, orientation, local_idx)
            after = len(pruned)

            # update the entry's segment list
            entry["segments"] = pruned

            # If changed, drop any word candidate whose 3-slice is not in pruned
            if after < before:
                w = words[wid]
                new_poss = [
                    cand
                    for cand in w.possibilities
                    if cand[slice_idx : slice_idx + 3] in pruned
                ]
                if not new_poss:  # contradiction
                    return []
                if len(new_poss) < len(w.possibilities):
                    w.possibilities = new_poss

        # after pruning every slot in this block, run AC-3 again
        words, square_map = ac3_reduce(words, square_map)
        if words is None:  # contradiction bubbled up
            return []

    # 4) rest of the pipeline
    filled = fill_in_squares_one_possibility(grid, square_map)
    words_in_grid = get_words_in_grid(filled)
    if contains_duplicate(words_in_grid):
        return []

    has_bad_pair, error_msg = contains_bad_word_pairs(
        words_in_grid, ctx.bad_pairs, ctx.contains
    )
    if has_bad_pair:
        return []

    br = choose_branch_square(square_map, heuristic)
    if br is None:
        # Grid is fully filled
        return [filled]
    x, y = br
    out = []
    for ch in sorted(square_map[(x, y)].possible_chars):
        new = filled.copy()
        new[x] = new[x][:y] + ch + new[x][y + 1 :]
        out.append(new)
    return out
