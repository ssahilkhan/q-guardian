"""Shared text normalization + near-duplicate index for the training-diversity audit."""

from __future__ import annotations

import collections
import re

_PUNCT = re.compile(r"[\s\W_]+", flags=re.UNICODE)


def normalize(text: str) -> str:
    t = text.lower().strip()
    t = _PUNCT.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def shingles(text: str, k: int = 5) -> set[str]:
    n = normalize(text)
    if len(n) < k:
        return {n} if n else set()
    return {n[i:i + k] for i in range(len(n) - k + 1)}


class NearDupIndex:
    """Inverted shingle index over reference texts for fast near-duplicate lookup."""

    def __init__(self, texts: list[str], k: int = 5) -> None:
        self.ref_sets = [shingles(t, k) for t in texts]
        self.postings: dict[str, list[int]] = {}
        for i, s in enumerate(self.ref_sets):
            for sh in s:
                self.postings.setdefault(sh, []).append(i)

    def max_jaccard(self, text: str, k: int = 5) -> tuple[float, int]:
        s = shingles(text, k)
        if not s:
            return 0.0, -1
        cnt: collections.Counter = collections.Counter()
        for sh in s:
            for i in self.postings.get(sh, ()):
                cnt[i] += 1
        best, best_i = 0.0, -1
        for i, shared in cnt.items():
            j = shared / (len(s) + len(self.ref_sets[i]) - shared)
            if j > best:
                best, best_i = j, i
        return best, best_i
