"""Command line interface: fill, show, check, seed, prune."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional, Sequence, Set

from . import __version__
from .context import BuilderConfig
from .filters import contains_bad_word_pairs, load_bad_pairs, load_contains_words
from .grid import (
    C_UNKNOWN,
    Direction,
    Grid,
    TemplateError,
    dims,
    format_grid,
    get_entries,
    get_words_in_grid,
    parse_templates,
    read_template,
    read_templates,
    str_to_grid,
)
from .runner import STATE_FILE, RunOptions, run_search
from .seed import make_seed_grids, parse_placement
from .wordlist import load_word_set, load_wordlist


def default_workers() -> int:
    return max(1, (os.cpu_count() or 2) - 1)


# ───────────────────────── shared argument groups ─────────────────────────────
def _add_wordlist_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--wordlist", required=True, metavar="FILE",
                   help="text file, 'WORD;SCORE' or one word per line")
    p.add_argument("--min-score", type=float, default=0, metavar="N",
                   help="keep scored words with score >= N (default 0). Unscored words are kept")
    p.add_argument("--min-length", type=int, default=3, metavar="N",
                   help="shortest word to load (default 3)")
    p.add_argument("--max-length", type=int, default=None, metavar="N",
                   help="longest word to load (default: the larger grid dimension)")
    p.add_argument("--bad-words", metavar="FILE",
                   help="words to leave out of the wordlist, one per line")
    p.add_argument("--bad-pairs", metavar="FILE",
                   help="pairs of words that may not share a grid, one pair per line")
    p.add_argument("--contains-words", metavar="FILE",
                   help="lines of 'ANSWER WORD WORD ...'. Two answers that contain "
                        "the same word may not share a grid")


def _load_words(args, grids: Sequence[Grid]) -> List[str]:
    height, width = dims(grids[0])
    max_length = args.max_length if args.max_length is not None else max(height, width)
    exclude: Set[str] = load_word_set(args.bad_words) if args.bad_words else set()
    return load_wordlist(
        args.wordlist,
        min_score=args.min_score,
        min_length=args.min_length,
        max_length=max_length,
        exclude=exclude,
    )


def _load_filters(args):
    bad_pairs = load_bad_pairs(args.bad_pairs) if args.bad_pairs else frozenset()
    contains = load_contains_words(args.contains_words) if args.contains_words else {}
    return bad_pairs, contains


# ───────────────────────── fill ───────────────────────────────────────────────
def cmd_fill(args) -> int:
    grids = read_templates(args.template)
    words = _load_words(args, grids)
    bad_pairs, contains = _load_filters(args)

    # Entries that are already complete in the template are accepted as
    # words for this run even if the wordlist does not have them.
    word_set = set(words)
    added: List[str] = []
    for grid in grids:
        for _, _, _, text in get_entries(grid):
            if C_UNKNOWN not in text and text not in word_set:
                word_set.add(text)
                words.append(text)
                added.append(text)

    height, width = dims(grids[0])
    if not args.quiet:
        print("=" * 60)
        print(f"  Template:     {args.template} ({height} rows x {width} columns, "
              f"{len(grids)} starting grid(s))")
        print(f"  Wordlist:     {args.wordlist}")
        print(f"  Total words:  {len(words)}")
        print(f"  Bad pairs:    {len(bad_pairs)}")
        print(f"  Workers:      {args.workers}")
        print("=" * 60)
        if added:
            print(f"Added {len(added)} template entries that are not in the wordlist: "
                  f"{', '.join(added)}")

    have_lengths = {len(w) for w in words}
    need_lengths = {len(text) for grid in grids for _, _, _, text in get_entries(grid)}
    missing = sorted(need_lengths - have_lengths)
    if missing:
        print(f"warning: the wordlist has no words of length {', '.join(map(str, missing))}. "
              "Entries of that length cannot be filled (see --min-length / --max-length).",
              file=sys.stderr)

    config = BuilderConfig(
        words=tuple(words),
        bad_pairs=bad_pairs,
        contains=contains,
        block_pruning=not args.no_block_pruning,
        verbose=args.verbose,
    )
    options = RunOptions(
        workers=args.workers,
        chunk_size=args.chunk_size,
        plateau=args.plateau,
        buffer=args.buffer,
        seed=args.seed,
        max_solutions=args.max_solutions,
        out_dir=args.out,
        resume=args.resume,
        overwrite=args.overwrite,
        quiet=args.quiet,
    )
    result = run_search(list(grids), config, options)
    if not args.quiet and result.state_path:
        print(f"Results: {result.state_path}  "
              f"(view with: crossword-builder show {result.state_path})")
    return 0


# ───────────────────────── show ───────────────────────────────────────────────
def _grids_from_file(path: str, width: Optional[int]) -> List[Grid]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    stripped = text.lstrip("﻿ \t\r\n")
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return parse_templates(text)

    data = json.loads(text)
    if isinstance(data, dict):
        solutions = data.get("solutions", [])
        width = width or data.get("width")
    else:
        solutions = data

    grids: List[Grid] = []
    for sol in solutions:
        if isinstance(sol, list):
            grids.append([str(row) for row in sol])
            continue
        if not width:
            raise ValueError(f"{path} does not record the grid width. Pass --width N.")
        grids.append(str_to_grid(sol, int(width)))
    return grids


def cmd_show(args) -> int:
    grids = _grids_from_file(args.file, args.width)
    shown = grids if args.limit is None else grids[: args.limit]
    for i, grid in enumerate(shown, start=1):
        print(f"# {i}")
        if args.wide:
            print("\n".join(" ".join(row) for row in grid))
        else:
            print(format_grid(grid))
        print()
    print(f"{len(grids)} grid(s) in {args.file}" +
          (f", {len(shown)} shown" if len(shown) != len(grids) else ""))
    return 0


# ───────────────────────── check ──────────────────────────────────────────────
def cmd_check(args) -> int:
    grids = read_templates(args.grid)
    words = set(_load_words(args, grids))
    bad_pairs, contains = _load_filters(args)

    failed = False
    for i, grid in enumerate(grids, start=1):
        problems: List[str] = []
        entries = get_entries(grid)
        for r, c, direction, text in entries:
            where = f"row {r + 1}, column {c + 1}, {'across' if direction == Direction.ACROSS else 'down'}"
            if C_UNKNOWN in text:
                problems.append(f"{text} ({where}) is not filled in")
            elif text not in words:
                problems.append(f"{text} ({where}) is not in the wordlist")

        has_bad_pair, message = contains_bad_word_pairs(
            get_words_in_grid(grid), bad_pairs, contains
        )
        if has_bad_pair and message:
            problems.append(message)

        if problems:
            failed = True
            print(f"grid {i}: {len(problems)} problem(s)")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"grid {i}: OK, all {len(entries)} entries are words")
    return 1 if failed else 0


# ───────────────────────── seed ───────────────────────────────────────────────
def cmd_seed(args) -> int:
    template = read_template(args.template)
    placements = [parse_placement(spec) for spec in args.place]
    grids, notes = make_seed_grids(template, placements)
    for note in notes:
        print(note, file=sys.stderr)
    if not grids:
        print("error: no combination of the placements fits the template", file=sys.stderr)
        return 1

    text = "\n\n".join(format_grid(g) for g in grids) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {len(grids)} starting grid(s) to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


# ───────────────────────── prune ──────────────────────────────────────────────
def cmd_prune(args) -> int:
    """Drop queued grids that already contain a word from the bad-words file."""
    path = args.state
    if os.path.isdir(path):
        path = os.path.join(path, STATE_FILE)
    rejected = load_word_set(args.bad_words)
    if not rejected:
        print("The bad-words file is empty. Nothing to filter.")
        return 0

    with open(path, "r", encoding="utf-8") as f:
        combined = json.load(f)

    snapshot = combined.get("snapshot", {})
    total = sum(len(grids) for grids in snapshot.values())
    filtered = {}
    removed = 0
    for depth, grids in snapshot.items():
        kept = []
        for grid in grids:
            overlap = rejected & set(get_words_in_grid(grid))
            if overlap:
                removed += 1
                print(f"Removing grid at depth {depth} containing: {', '.join(sorted(overlap))}")
            else:
                kept.append(grid)
        if kept:
            filtered[depth] = kept

    combined["snapshot"] = filtered
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=4, ensure_ascii=False)
    os.replace(tmp, path)

    print(f"Original grids: {total}")
    print(f"Removed:        {removed}")
    print(f"Remaining:      {total - removed}")
    print(f"Saved to:       {path}")
    return 0


# ───────────────────────── parser ─────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crossword-builder",
        description="Fill crossword grids from a template and a wordlist.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fill", help="search for fills of a template")
    p.add_argument("template", help="template text file (one row per line)")
    _add_wordlist_args(p)
    p.add_argument("--workers", type=int, default=default_workers(), metavar="N",
                   help="worker processes (default: CPU count minus one). "
                        "1 runs in-process without multiprocessing")
    p.add_argument("--chunk-size", type=int, default=40, metavar="N",
                   help="grids handed to each worker per batch (default 40)")
    p.add_argument("--out", default="outputs", metavar="DIR",
                   help=f"output directory (default 'outputs'). State is kept in DIR/{STATE_FILE}")
    p.add_argument("--resume", action="store_true",
                   help="continue from the snapshot in the output directory")
    p.add_argument("--overwrite", action="store_true",
                   help="start over even if the output directory already holds a search")
    p.add_argument("--max-solutions", type=int, default=None, metavar="N",
                   help="stop after the batch in which N new solutions have been found")
    p.add_argument("--seed", type=int, default=None, help="seed for the batch shuffle")
    p.add_argument("--plateau", action="store_true",
                   help="plateau-skipping mode: hold back the deepest grids and work below them")
    p.add_argument("--buffer", type=int, default=0, metavar="N",
                   help="with --plateau: hold back grids within N levels of the deepest (default 0)")
    p.add_argument("--no-block-pruning", action="store_true",
                   help="use the plain AC-3 search step without 3x3 block pruning")
    p.add_argument("--quiet", action="store_true", help="print nothing but errors")
    p.add_argument("--verbose", action="store_true",
                   help="with --no-block-pruning: print every rejected grid")
    p.set_defaults(func=cmd_fill)

    p = sub.add_parser("show", help="print the grids in a solutions file")
    p.add_argument("file", help=f"a {STATE_FILE} written by 'fill', or a text file of grids")
    p.add_argument("--limit", type=int, default=None, metavar="N", help="show at most N grids")
    p.add_argument("--width", type=int, default=None, metavar="N",
                   help="grid width, for JSON files that do not record it")
    p.add_argument("--wide", action="store_true", help="put a space between cells")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("check", help="check that every entry of a grid is a word")
    p.add_argument("grid", help="text file with one or more filled grids")
    _add_wordlist_args(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("seed", help="place seed entries into a template to make starting grids")
    p.add_argument("template", help="template text file")
    p.add_argument("--place", action="append", required=True, metavar="ROW,COL,DIR,WORD",
                   help="0-based first cell, 'across' or 'down', and the word. "
                        "Alternatives: WORD1|WORD2. Repeat --place for more entries")
    p.add_argument("-o", "--output", metavar="FILE", help="write here instead of stdout")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("prune", help="drop queued grids that contain a bad word")
    p.add_argument("state", help=f"output directory of a search, or its {STATE_FILE}")
    p.add_argument("--bad-words", required=True, metavar="FILE", help="one word per line")
    p.set_defaults(func=cmd_prune)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (TemplateError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
