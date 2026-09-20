# Crossword Constructor

You give it a grid template (the walls, plus any entries you already want) and a wordlist. It searches for ways to fill the rest, so that every across and down entry is a word from the list. It saves every fill it finds, so you choose among options.

It is a command line tool and a small Python package. The core uses only the standard library. Grids can be any rectangular size.

I wrote it to build my own puzzles. `examples/moody-foods` is one of them.

## Install

Python 3.10 or newer. Clone this repo, then from the repo root:

```
pip install .
```

For progress bars, install with the optional extra:

```
pip install ".[progress]"
```

You can also run it without installing:

```
PYTHONPATH=src python3 -m crossword_constructor --help
```

## Quickstart

The search needs a wordlist. No wordlist is included in this repo. Mine is public, in a separate repo with its own license (CC BY-NC-SA 4.0). Download it:

```
curl -L -o matts_wordlist.txt https://raw.githubusercontent.com/mattabate/wordlist/refs/heads/main/quickstart/matts_wordlist.txt
```

Fill the example template:

```
crossword-constructor fill examples/moody-foods/template.txt --wordlist matts_wordlist.txt --out outputs/moody-foods
```

The search runs until it has tried everything or until you stop it with Ctrl-C. Fills are written as they are found:

- `outputs/moody-foods/solutions.txt` holds every fill, as plain grids.
- `outputs/moody-foods/combined.json` holds the fills and the queue of partial grids.

Continue a stopped search:

```
crossword-constructor fill examples/moody-foods/template.txt --wordlist matts_wordlist.txt --out outputs/moody-foods --resume
```

Look at the results, or check a finished grid against a wordlist:

```
crossword-constructor show outputs/moody-foods/combined.json --limit 5
crossword-constructor check examples/moody-foods/solution.txt --wordlist matts_wordlist.txt
```

### Wordlist formats

A wordlist is a text file. Each line is either `WORD;SCORE` or just `WORD`. Words are uppercased. Spaces, hyphens and apostrophes are removed. Lines that still contain anything other than A to Z are skipped.

### Options for `fill`

| Option | Meaning |
|---|---|
| `--wordlist FILE` | The wordlist. Required. |
| `--min-score N` | Keep scored words with a score of at least N. Words without a score are always kept. Default 0. |
| `--min-length N` | Shortest word to load. Default 3. |
| `--max-length N` | Longest word to load. Default is the larger grid dimension. |
| `--bad-words FILE` | Words to leave out, one per line. |
| `--bad-pairs FILE` | Pairs of words that may not appear in the same grid, one pair per line. |
| `--contains-words FILE` | Lines of `ANSWER WORD WORD ...`. Two answers that contain the same word may not appear in the same grid. |
| `--workers N` | Worker processes. Default is the CPU count minus one. `--workers 1` runs in a single process without multiprocessing. |
| `--chunk-size N` | Grids given to each worker per batch. Default 40. |
| `--out DIR` | Output directory. Default `outputs`. |
| `--resume` | Continue from the snapshot in the output directory. |
| `--overwrite` | Start over even if the output directory holds a search. |
| `--max-solutions N` | Stop after the batch in which N fills have been found. |
| `--seed N` | Seed for the batch shuffle. |
| `--plateau`, `--buffer N` | Hold back the deepest grids and work on shallower ones first. |
| `--no-block-pruning` | Use the plain search step (see below). |
| `--quiet`, `--verbose` | Less or more output. |

`fill` refuses to write into an output directory that already holds a search unless you pass `--resume` or `--overwrite`.

Two more commands:

- `crossword-constructor seed TEMPLATE --place ROW,COL,DIR,WORD` writes theme entries into a template. ROW and COL are 0-based. DIR is `across` or `down`. `WORD1|WORD2` gives alternatives, and one starting grid is made for each combination that fits.
- `crossword-constructor prune DIR --bad-words FILE` removes queued partial grids that already contain a word you have since rejected. Use it before `--resume`.

## Template format

A template is a text file with one grid row per line. Every row must have the same length. The grid does not have to be square.

| Character | Meaning |
|---|---|
| `█` or `#` | Wall (black square) |
| `.` or `@` | Open cell, letter unknown |
| `A` to `Z` | Open cell with a fixed letter. Lowercase is accepted. |

Example, 9 rows by 11 columns, with two theme entries fixed:

```
....#......
....#......
....#......
#BLUEBERRY#
##...#...##
#SOURCREAM#
......#....
......#....
......#....
```

Rules:

- Every open cell must be part of an across entry and a down entry of at least two cells. Templates with unchecked cells are rejected.
- Entries of length 2 are only fillable if you pass `--min-length 2` and the wordlist has two letter words.
- A fixed entry that is already complete is accepted even if it is not in the wordlist. `fill` tells you when it does this.
- A file may hold several grids of the same size, separated by blank lines. All of them go into the starting queue.

Output grids use `█` for walls.

## How the search works

The search is a depth-first tree search over partial grids. Each step takes one partial grid and produces its children.

**Pattern lookup.** Words are grouped by length. For each length there is an index from (position, letter) to the set of words with that letter there. The candidates for a pattern like `B..E` are the intersection of those sets. Each distinct pattern is computed once and cached.

**AC-3.** Every entry keeps a list of candidate words. Every cell keeps a set of candidate letters. Two rules are applied until nothing changes. An entry drops the candidates that use a letter one of its cells no longer allows. A cell keeps only the letters that are offered by both its across entry and its down entry. If any entry or cell runs out of options, the grid is dead and has no children.

**3x3 block pruning.** AC-3 looks at one cell at a time, so it misses conflicts that involve several cells. After AC-3, the search looks at every fully open 3x3 block of cells. Three across entries and three down entries pass through a block. For each, it collects the distinct 3 letter segments its candidates would put inside the block. A segment survives only if three crossing segments can spell it while their other rows (or columns) are also available segments. Candidates whose segment did not survive are dropped, and AC-3 runs again. This is expensive, so it only runs on blocks where the candidate letter counts of the nine cells sum to more than 35 and less than 90, and on entries with 2 to 99 distinct segments.

**Forced letters and filters.** Every cell with one candidate letter is written into the grid. Then the completed entries are checked. The grid is dropped if a word appears twice, if two words form a listed bad pair, or if two answers contain the same listed word.

**Branching.** One undecided cell is chosen. Cells where the row index and the column index are both even are preferred. Among those, the cell with the fewest candidate letters wins. Ties go to the first cell in reading order. The step returns one child grid per candidate letter of that cell. If no cell is undecided, the grid is a solution.

**The plain step.** With `--no-block-pruning` the block pruning is skipped, and the branching rule changes. The search builds a graph that links each unfilled cell to the next undecided cell to its right and below it within the same entry. It uses union-find to find the components of that graph that have no cycle. Cells in those components, and cells that are the last open cell of both their entries, are skipped when choosing where to branch. They are only branched on when nothing else is left.

**The queue.** Partial grids wait in a queue, each with its depth (the number of branching steps behind it). Each batch takes the deepest `workers x chunk-size` grids, shuffles them, and deals them out to the workers. Children that are complete are saved as solutions. The rest go back into the queue one level deeper. Working deepest first keeps the queue small and reaches full grids early.

**Plateau mode.** With `--plateau`, the grids within `--buffer` levels of the deepest level are held back, and the batch is taken from the shallower grids. If every grid is that deep, the batch is taken from them anyway.

**Workers.** Worker processes are started once with the `spawn` method. Each one builds its own word index. With `--workers 1` no processes are started.

**Snapshots.** After every batch the solutions and the queue are written to `combined.json`. The write goes to a temporary file that then replaces the old one, so an interrupted run leaves a usable snapshot.

The search is exhaustive. If it ends on its own, it has found every fill that the wordlist and the filters allow. On an open grid with a large wordlist that can take a very long time, so the normal use is to let it run, read fills as they arrive, and stop it when you have one you like.

## The example

`examples/moody-foods` holds Moody Foods, a 9x11 puzzle I built with this tool for a Puzzmo submission. It has the template, the finished grid, and the puzzle as `.puz` and `.pdf`. You can play it at https://mattabate.com/puzzles/moodyfoods.

## Use as a library

```python
from crossword_constructor import RunOptions, ConstructorConfig, load_wordlist, read_template, run_search

if __name__ == "__main__":
    grid = read_template("examples/moody-foods/template.txt")
    words = load_wordlist("matts_wordlist.txt", min_length=3, max_length=11)
    words += ["BLUEBERRY", "SOURCREAM"]  # fixed entries must be in the list
    result = run_search(
        [grid],
        ConstructorConfig(words=tuple(dict.fromkeys(words))),
        RunOptions(workers=4, out_dir="outputs/moody-foods", max_solutions=10),
    )
    for solution in result.solutions:
        print("\n".join(solution), end="\n\n")
```

Keep the `if __name__ == "__main__":` guard. Worker processes import your script again when they start.

## Tests

```
python3 -m unittest discover -s tests -t .
```

## Related

- My wordlist: https://github.com/mattabate/wordlist
- My other projects: https://mattabate.com/projects

## License

MIT. See `LICENSE`. The wordlist is a separate project with its own license and is not included here.
