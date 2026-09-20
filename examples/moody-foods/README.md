# Moody Foods

A 9 row by 11 column crossword. I built it with this tool for a Puzzmo submission.

Play it at https://mattabate.com/puzzles/moodyfoods

## Files

| File | What it is |
|---|---|
| `template.txt` | The wall pattern with the two theme entries, BLUEBERRY and SOURCREAM, placed. |
| `solution.txt` | The finished grid, as published. |
| `Moody Foods.puz` | The finished puzzle with clues, in Across Lite format. |
| `Moody Foods.pdf` | The finished puzzle with clues, for printing. |

## Reproduce

Run these from the repo root. The first line downloads my wordlist. It is not part of this repo.

```
curl -L -o matts_wordlist.txt https://raw.githubusercontent.com/mattabate/wordlist/refs/heads/main/quickstart/matts_wordlist.txt
crossword-constructor fill "examples/moody-foods/template.txt" --wordlist matts_wordlist.txt --out outputs/moody-foods
```

The search writes every fill it finds to `outputs/moody-foods/solutions.txt`.
Stop it with Ctrl-C at any time. Add `--resume` to the same command to continue.

A template like this has many fills. The published grid is the one I picked.
The search can only reach it if every one of its entries is in the wordlist you load.
Which fills come first depends on the wordlist, on `--min-score` and on `--seed`.

To check the published grid against a wordlist:

```
crossword-constructor check "examples/moody-foods/solution.txt" --wordlist matts_wordlist.txt
```

`check` lists any entry of the grid that is not in the wordlist.
