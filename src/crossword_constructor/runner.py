"""The search driver: a frontier of partial grids, processed in batches.

* The frontier is a list of (grid, depth) pairs. Depth is the number of
  branching steps taken from the starting grid.
* Each batch takes the deepest ``workers * chunk_size`` grids, shuffles them
  and deals them out to the workers.
* A worker expands each grid into its children. Complete children are
  solutions. Incomplete children go back to the frontier at depth + 1.
* After every batch the solutions and the frontier are written to
  ``<out>/combined.json`` so a run can be stopped and resumed.

With ``workers == 1`` everything runs in the calling process and no
multiprocessing is used.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import random
import signal
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .context import ConstructorConfig, ConstructorContext
from .filters import contains_bad_word_pairs
from .grid import (
    C_UNKNOWN,
    Grid,
    TemplateError,
    dims,
    format_grid,
    get_words_in_grid,
    grid_contains_grid,
    str_to_grid,
    validate_grid,
)
from .pruning import super_get_new_grids
from .search import cell_heuristic, get_new_grids

try:  # optional dependency
    from tqdm import tqdm as _tqdm
except Exception:  # pragma: no cover - tqdm not installed
    _tqdm = None

Frontier = List[Tuple[Grid, int]]  # (grid, depth)

STATE_FILE = "combined.json"
SOLUTIONS_TXT = "solutions.txt"


@dataclass
class RunOptions:
    workers: int = 1
    chunk_size: int = 40  # grids per worker per batch
    plateau: bool = False  # plateau-skipping mode
    buffer: int = 0  # plateau mode: depth band below the deepest level that is held back
    seed: Optional[int] = None  # seed for the batch shuffle
    max_solutions: Optional[int] = None  # stop after this many new solutions
    out_dir: Optional[str] = None  # None keeps all state in memory
    resume: bool = False
    overwrite: bool = False
    quiet: bool = False


@dataclass
class RunResult:
    solutions: List[Grid] = field(default_factory=list)  # new solutions from this run
    batches: int = 0
    exhausted: bool = False
    interrupted: bool = False
    state_path: Optional[str] = None


# ───────────────────────── one unit of work ───────────────────────────────────
def expand(grid: Grid, ctx: ConstructorContext) -> List[Grid]:
    """Expand one grid with the configured search step."""
    if ctx.config.block_pruning:
        return super_get_new_grids(grid, ctx, cell_heuristic)
    return get_new_grids(grid, ctx, cell_heuristic)


def worker_loop(in_queue: Frontier, ctx: ConstructorContext, progress: bool = False):
    """Expand every grid of a chunk.

    Returns (children, solutions, count): incomplete children as
    (grid, depth) pairs, complete children as flat strings, and the total
    number of children produced.
    """
    children_out: Frontier = []
    solutions: List[str] = []
    count = 0

    items = in_queue
    if progress and _tqdm is not None:
        items = _tqdm(in_queue, leave=False)

    for grid, depth in items:
        for child in expand(grid, ctx):
            if C_UNKNOWN not in "".join(child):
                # NOTE (differs from the original script): a child completed by
                # the branching letter itself was saved without passing through
                # the duplicate / bad pair filters, because those run before
                # branching. Check it here so every saved grid respects them.
                if ctx.config.validate_solutions:
                    rejected, _ = contains_bad_word_pairs(
                        get_words_in_grid(child), ctx.bad_pairs, ctx.contains
                    )
                    if rejected:
                        continue
                solutions.append("".join(child))
            else:
                children_out.append((child, depth + 1))
            count += 1

    return children_out, solutions, count


# Worker processes are started with the "spawn" method. Each one builds its
# own context from the pickled config, once, in the pool initializer.
_WORKER_CTX: Optional[ConstructorContext] = None


def _init_worker(config: ConstructorConfig) -> None:
    global _WORKER_CTX
    # Ctrl-C belongs to the parent, which saves the snapshot and stops the pool.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _WORKER_CTX = ConstructorContext(config)


def _run_chunk(chunk: Frontier):
    return worker_loop(chunk, _WORKER_CTX)


# ───────────────────────── state file ─────────────────────────────────────────
class _State:
    """The combined solutions + snapshot document, on disk or in memory."""

    def __init__(self, path: Optional[str]):
        self.path = path
        self._memory: Dict = {}

    def exists(self) -> bool:
        return self.path is not None and os.path.exists(self.path)

    def load(self) -> Dict:
        if self.path is None:
            return self._memory
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data: Dict) -> None:
        if self.path is None:
            self._memory = data
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, self.path)


def snapshot_queue(frontier: Frontier, state: _State) -> None:
    """Save the incomplete grids, grouped by depth. Solutions are preserved."""
    snap: Dict[str, List[Grid]] = defaultdict(list)
    for grid, depth in sorted(frontier, key=lambda x: x[1]):  # shallow to deep
        if C_UNKNOWN in "".join(grid):
            snap[str(depth)].append(grid)

    combined = state.load()
    combined["snapshot"] = dict(snap)
    state.save(combined)


def save_solutions(batch_solutions: List[str], state: _State) -> List[str]:
    """Add the solutions that are not already saved. Returns the new ones."""
    combined = state.load()
    existing = combined.get("solutions", [])
    existing_set = set(existing)

    new_solutions: List[str] = []
    for sol in batch_solutions:
        if sol not in existing_set and not any(grid_contains_grid(g, sol) for g in existing):
            new_solutions.append(sol)
            existing.append(sol)
            existing_set.add(sol)

    if new_solutions:
        combined["solutions"] = existing
        state.save(combined)
    return new_solutions


def load_frontier(combined: Dict) -> Frontier:
    return [
        (list(rows), int(depth))
        for depth, grids in combined.get("snapshot", {}).items()
        for rows in grids
    ]


# ───────────────────────── main driver loop ───────────────────────────────────
def run_search(
    start_grids: List[Grid], config: ConstructorConfig, options: Optional[RunOptions] = None
) -> RunResult:
    opts = options or RunOptions()
    if opts.workers < 1:
        raise ValueError("workers must be at least 1")
    if opts.chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    if not start_grids:
        raise TemplateError("no starting grid given")

    def log(msg: str = "") -> None:
        if opts.quiet:
            return
        if _tqdm is not None:
            _tqdm.write(msg)
        else:
            print(msg)

    height, width = dims(start_grids[0])
    for g in start_grids:
        if dims(g) != (height, width):
            raise TemplateError(
                f"all starting grids must have the same size: found {dims(g)[0]}x{dims(g)[1]} "
                f"and {height}x{width} (rows x columns)"
            )
        validate_grid(g)

    # state ----------------------------------------------------------------
    state_path = None
    if opts.out_dir is not None:
        os.makedirs(opts.out_dir, exist_ok=True)
        state_path = os.path.join(opts.out_dir, STATE_FILE)
    state = _State(state_path)
    result = RunResult(state_path=state_path)

    if state.exists() and opts.resume:
        combined = state.load()
        frontier = load_frontier(combined)
        saved_dims = (combined.get("height"), combined.get("width"))
        if saved_dims == (None, None) and frontier:
            saved_dims = dims(frontier[0][0])
        if saved_dims != (None, None) and saved_dims != (height, width):
            raise TemplateError(
                f"{state_path} holds {saved_dims[0]}x{saved_dims[1]} grids but the template "
                f"is {height}x{width} (rows x columns)"
            )
        if not frontier:
            log(
                f"The snapshot in {state_path} is empty: that search has finished. "
                f"{len(combined.get('solutions', []))} solution(s) are saved there."
            )
            result.exhausted = True
            return result
        log(f"Resuming from {state_path}: {len(frontier)} grids in the queue.")
    else:
        if state.exists() and not opts.overwrite:
            raise FileExistsError(
                f"{state_path} already exists. Use --resume to continue that search, "
                "--overwrite to start over, or choose another --out directory."
            )
        frontier = [(list(g), 0) for g in start_grids]
        state.save(
            {
                "height": height,
                "width": width,
                "solutions": [],
                "snapshot": {"0": [list(g) for g in start_grids]},
            }
        )
        if opts.out_dir is not None:
            with open(os.path.join(opts.out_dir, SOLUTIONS_TXT), "w", encoding="utf-8"):
                pass

    rng = random.Random(opts.seed)
    batch_size = opts.workers * opts.chunk_size

    ctx: Optional[ConstructorContext] = None
    pool = None
    if opts.workers == 1:
        ctx = ConstructorContext(config)
    else:
        pool = multiprocessing.get_context("spawn").Pool(
            processes=opts.workers, initializer=_init_worker, initargs=(config,)
        )

    # search loop ----------------------------------------------------------
    try:
        while frontier:
            result.batches += 1

            frontier.sort(key=lambda x: x[1], reverse=True)  # deepest first

            if opts.plateau:  # plateau-skipping mode
                max_depth = frontier[0][1]
                plateau = [it for it in frontier if it[1] >= max_depth - opts.buffer]
                candidates = [it for it in frontier if it[1] < max_depth - opts.buffer]

                # If everything is on the plateau, process it anyway
                if not candidates:
                    candidates, plateau = plateau, []

                batch = candidates[:batch_size]
                frontier = candidates[batch_size:] + plateau
            else:
                batch, frontier = frontier[:batch_size], frontier[batch_size:]

            rng.shuffle(batch)
            chunks: List[Frontier] = [[] for _ in range(opts.workers)]
            for idx, item in enumerate(batch):
                chunks[idx % opts.workers].append(item)

            jobs = [(wid, chunk) for wid, chunk in enumerate(chunks) if chunk]
            if pool is None:
                outputs = [
                    worker_loop(chunk, ctx, progress=not opts.quiet) for _, chunk in jobs
                ]
            else:
                outputs = pool.map(_run_chunk, [chunk for _, chunk in jobs])

            # Collect incomplete grids for the next iteration, and solutions
            batch_solutions: List[str] = []
            stats: Dict[int, Tuple[int, int]] = {}
            for (wid, _), (children, sols, count) in zip(jobs, outputs):
                frontier.extend(children)
                batch_solutions.extend(sols)
                stats[wid] = (count, len(sols))

            if batch_solutions:
                new_solutions = save_solutions(batch_solutions, state)
                if new_solutions:
                    log(f"Saved {len(new_solutions)} new solution(s).")
                    for sol_str in new_solutions[:3]:  # show the first 3
                        log(format_grid(str_to_grid(sol_str, width)))
                        log()
                    if len(new_solutions) > 3:
                        log(f"   ... and {len(new_solutions) - 3} more")
                    if opts.out_dir is not None:
                        path = os.path.join(opts.out_dir, SOLUTIONS_TXT)
                        with open(path, "a", encoding="utf-8") as f:
                            for sol_str in new_solutions:
                                f.write(format_grid(str_to_grid(sol_str, width)) + "\n\n")
                    result.solutions.extend(str_to_grid(s, width) for s in new_solutions)

            # batch summary
            log(f"\n=== Batch {result.batches} results ===")
            total_produced = 0
            total_solutions = 0
            for wid, chunk in enumerate(chunks):
                worker_total, worker_sols = stats.get(wid, (0, 0))
                log(
                    f"  - worker {wid}: {len(chunk):3d} grids -> {worker_total} children "
                    f"({worker_sols} solutions)"
                )
                total_produced += worker_total - len(chunk)
                total_solutions += worker_sols
            log(f"total produced = {total_produced} ({total_solutions} solutions)")
            depth_hist: Dict[int, int] = defaultdict(int)
            for _, d in frontier:
                depth_hist[d] += 1
            hist_str = "  ".join(f"d{d}:{c}" for d, c in sorted(depth_hist.items()))
            log(f"in-queue:{len(frontier):>7}   {hist_str}")
            snapshot_queue(frontier, state)
            if state_path is not None:
                log(f"Queue snapshot written to {state_path}")
            log(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            if opts.max_solutions is not None and len(result.solutions) >= opts.max_solutions:
                log(f"Reached {len(result.solutions)} solution(s). Stopping.")
                return result

        result.exhausted = True
        log(f"Search space exhausted. {len(result.solutions)} new solution(s) found.")
        return result
    except KeyboardInterrupt:
        result.interrupted = True
        if state_path is not None:
            log(f"\nInterrupted. The last snapshot is in {state_path}. Continue with --resume.")
        else:
            log("\nInterrupted.")
        return result
    finally:
        if pool is not None:
            pool.terminate()
            pool.join()
