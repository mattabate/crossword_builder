"""Whole-grid filters: duplicate words, bad word pairs, shared contained words.

All three are optional inputs kept in plain text files.

Bad pairs file: one pair per line, two words separated by a space, a comma
or a semicolon::

    SOURCREAM ICECREAM
    EAST,WEST

Contained words file: one answer per line, followed by the words it
contains. A grid is rejected when two of its answers contain the same word::

    SOURCREAM SOUR CREAM
    ICECREAM ICE CREAM
"""
from __future__ import annotations

import re
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

from .wordlist import normalize_word

_SPLIT = re.compile(r"[\s,;:]+")


def _tokens(line: str, path: str, line_no: int) -> List[str]:
    out = []
    for raw in _SPLIT.split(line.strip()):
        if not raw:
            continue
        word = normalize_word(raw)
        if word is None:
            raise ValueError(f"{path}, line {line_no}: {raw!r} is not a word")
        out.append(word)
    return out


def load_bad_pairs(path: str) -> FrozenSet[FrozenSet[str]]:
    """Load bad pairs as a frozenset of two-word frozensets."""
    pairs = set()
    with open(path, "r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            words = _tokens(line, path, line_no)
            if len(words) != 2:
                raise ValueError(
                    f"{path}, line {line_no}: expected two words, found {len(words)}"
                )
            pairs.add(frozenset(words))
    return frozenset(pairs)


def load_contains_words(path: str) -> Dict[str, List[str]]:
    """Load the answer -> contained words map."""
    out: Dict[str, List[str]] = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            words = _tokens(line, path, line_no)
            if len(words) < 2:
                raise ValueError(
                    f"{path}, line {line_no}: expected an answer followed by the words it contains"
                )
            out.setdefault(words[0], []).extend(words[1:])
    return out


def contains_duplicate(words: Iterable[str]) -> bool:
    words = list(words)
    return len(words) != len(set(words))


def contains_bad_word_pairs(
    words: List[str],
    bad_pairs: FrozenSet[FrozenSet[str]] = frozenset(),
    contains: Optional[Dict[str, List[str]]] = None,
) -> Tuple[bool, Optional[str]]:
    """Check the completed words of a grid.

    Rejects a grid when:

    1. the same word appears twice
    2. two of its words form a pair listed in ``bad_pairs``
    3. two of its words both contain the same word according to ``contains``

    Returns (has_bad_pair, message).
    """
    words_set = set(words)

    # Check for duplicate words
    if len(words) != len(words_set):
        duplicates = sorted(w for w in words_set if words.count(w) > 1)
        return True, f"Duplicate word(s): {', '.join(duplicates)}"

    # Check against the bad pairs
    if bad_pairs:
        for word in words:
            for other_word in words:
                if word != other_word:
                    if frozenset([word, other_word]) in bad_pairs:
                        return True, f"Bad pair: {word} + {other_word}"

    # Build reverse index: contained word -> answers in this grid that contain it
    if contains:
        contained_to_answers: Dict[str, List[str]] = {}
        for answer in words:
            if answer in contains:
                for contained_word in contains[answer]:
                    contained_to_answers.setdefault(contained_word, []).append(answer)

        # Find any contained word that appears in more than one answer
        for contained_word, answers_list in contained_to_answers.items():
            if len(answers_list) > 1:
                return (
                    True,
                    f"Bad pair: {' and '.join(answers_list)} both contain '{contained_word}'",
                )

    return False, None
