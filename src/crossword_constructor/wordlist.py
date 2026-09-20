"""Wordlist loading and the positional letter index used for pattern lookups.

Two text formats are accepted, and may be mixed in one file:

* ``WORD;SCORE`` per line (the format used by crossword construction software)
* one word per line, with no score

Words are uppercased. Spaces, hyphens and apostrophes are removed. Entries
that still contain anything other than A-Z are skipped. Blank lines are
ignored.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

_LETTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_DROP = str.maketrans("", "", " -'’\t")


def normalize_word(raw: str) -> Optional[str]:
    """Uppercase and clean one entry. Return None if it is not usable."""
    word = raw.strip().upper().translate(_DROP)
    if not word or not all(ch in _LETTERS for ch in word):
        return None
    return word


def parse_wordlist_line(line: str) -> Optional[Tuple[str, Optional[float]]]:
    """Parse one line into (word, score). The score is None when absent."""
    line = line.strip()
    if not line:
        return None
    parts = line.split(";")
    word = normalize_word(parts[0])
    if word is None:
        return None
    score: Optional[float] = None
    if len(parts) > 1 and parts[1].strip():
        try:
            score = float(parts[1].strip())
        except ValueError:
            score = None
    return word, score


def load_wordlist(
    path: str,
    min_score: Optional[float] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    exclude: Optional[Iterable[str]] = None,
) -> List[str]:
    """Load a wordlist file.

    * ``min_score``: keep scored words with ``score >= min_score``. Words
      without a score are always kept.
    * ``min_length`` / ``max_length``: inclusive length bounds.
    * ``exclude``: words to leave out (for example a bad-words file).

    File order is kept. Duplicates are dropped after the first occurrence.
    """
    excluded: Set[str] = set(exclude) if exclude else set()
    seen: Set[str] = set()
    words: List[str] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            parsed = parse_wordlist_line(line)
            if parsed is None:
                continue
            word, score = parsed
            if min_score is not None and score is not None and score < min_score:
                continue
            if min_length is not None and len(word) < min_length:
                continue
            if max_length is not None and len(word) > max_length:
                continue
            if word in excluded or word in seen:
                continue
            seen.add(word)
            words.append(word)
    return words


def load_word_set(path: str) -> Set[str]:
    """Load a plain list of words (for example bad words) as a set.

    The same line formats as a wordlist are accepted. Scores are ignored.
    """
    out: Set[str] = set()
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            parsed = parse_wordlist_line(line)
            if parsed is not None:
                out.add(parsed[0])
    return out


class WordIndex:
    """Words grouped by length, with a positional letter index.

    For each length the index stores, for each position, a map from letter
    to the set of word ids that have that letter there. A pattern lookup
    intersects those sets. Each distinct pattern is computed once and then
    served from a cache for the rest of the search.
    """

    def __init__(self, words: Iterable[str]):
        self.by_len: Dict[int, List[str]] = {}
        for w in words:
            self.by_len.setdefault(len(w), []).append(w)

        self._word_sets: Dict[int, Set[str]] = {
            length: set(ws) for length, ws in self.by_len.items()
        }
        self._tables: Dict[int, List[Dict[str, Set[int]]]] = {}
        for length, ws in self.by_len.items():
            pos_tables: List[Dict[str, Set[int]]] = [
                defaultdict(set) for _ in range(length)
            ]
            for idx, word in enumerate(ws):
                for pos, ch in enumerate(word):
                    pos_tables[pos][ch].add(idx)
            self._tables[length] = pos_tables

        self._cache: Dict[str, List[str]] = {}

    def __len__(self) -> int:
        return sum(len(ws) for ws in self.by_len.values())

    def __contains__(self, word: str) -> bool:
        return word in self._word_sets.get(len(word), ())

    def lengths(self) -> Set[int]:
        return set(self.by_len)

    def words_of_length(self, length: int) -> List[str]:
        """A fresh copy of every word of this length."""
        return self.by_len.get(length, [])[:]

    def candidates_for(self, pattern: str) -> List[str]:
        """All words matching ``pattern``, where ``.`` is a wildcard.

        The returned list is shared with the cache. Callers must not
        modify it in place.
        """
        cached = self._cache.get(pattern)
        if cached is not None:
            return cached
        result = self._candidates_for(pattern)
        self._cache[pattern] = result
        return result

    def _candidates_for(self, pattern: str) -> List[str]:
        length = len(pattern)
        words = self.by_len.get(length)
        if not words:  # no word of this length at all
            return []
        tables = self._tables[length]

        # Fully fixed pattern: membership test
        if "." not in pattern:
            return [pattern] if pattern in self._word_sets[length] else []

        # Gather required letter-position sets
        sets: List[Set[int]] = []
        for pos, ch in enumerate(pattern):
            if ch != ".":
                s = tables[pos].get(ch)
                if not s:  # no word has that letter here
                    return []
                sets.append(s)

        if not sets:  # pattern is all wildcards: every word fits
            return words[:]

        cand_ids = set.intersection(*sets)
        return [words[i] for i in cand_ids]
