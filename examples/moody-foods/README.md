# Moody Foods

A 9 row by 11 column crossword. I built it with this tool for a Puzzmo submission.

Play it at https://mattabate.com/puzzles/moodyfoods

## Files

| File | What it is |
|---|---|
| `template.txt` | The wall pattern with the two theme entries, BLUEBERRY and SOURCREAM, placed. |
| `template-quick.txt` | The same template with four more entries placed: DUFF, CRISPY, OOPSIE and DTEN. |
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

A template like this has many fills. With my wordlist and `--min-score 20`, four workers saved about 10,000 fills in 8 minutes.
The published grid is the one I picked. The search can only reach it if every one of its entries is loaded.
Its lowest scoring entry, FAILTOPAY, scores 11 in my wordlist, so it needs `--min-score 10` or lower.
Which fills come first depends on the wordlist, on `--min-score` and on `--seed`.

## The quick version

`template-quick.txt` has four more entries placed. That search ends on its own in a few seconds.
It finds 24 fills, and the published grid is one of them:

```
crossword-constructor fill "examples/moody-foods/template-quick.txt" --wordlist matts_wordlist.txt --min-score 10 --out outputs/moody-foods-quick
```

To check the published grid against a wordlist:

```
crossword-constructor check "examples/moody-foods/solution.txt" --wordlist matts_wordlist.txt
```

`check` lists any entry of the grid that is not in the wordlist.
