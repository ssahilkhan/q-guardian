"""Embedding explainability: per-call metadata and traces.

Every embedding produced through :class:`EmbeddingManager` carries an
:class:`EmbeddingMeta` record (provider, model, dimension, latency, cache
and fallback flags). Feature fusion attaches it to the feature dict, and
:class:`EmbeddingTrace` collects records for whole-run reporting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Any


@dataclass(frozen=True)
class EmbeddingMeta:
    """Metadata describing how one embedding was produced.

    Fields:
        provider: Provider registry name (e.g. ``minilm``, ``hash-ngram``).
        model: Model identifier (e.g. ``all-MiniLM-L6-v2``).
        dimension: Dimensionality of the produced vector.
        latency_ms: Compute latency in milliseconds (0 for cache hits).
        mode: Feature mode (``handcrafted``/``embedding``/``hybrid``), filled
            by the fusion layer; empty when not fused.
        cached: Whether the vector came from the cache.
        fallback: Whether a fallback provider produced the vector.
    """

    provider: str
    model: str
    dimension: int
    latency_ms: float = 0.0
    mode: str = ""
    cached: bool = False
    fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbeddingMeta:
        return cls(
            provider=str(data["provider"]),
            model=str(data["model"]),
            dimension=int(data["dimension"]),
            latency_ms=float(data.get("latency_ms", 0.0)),
            mode=str(data.get("mode", "")),
            cached=bool(data.get("cached", False)),
            fallback=bool(data.get("fallback", False)),
        )

    @property
    def is_cache_hit(self) -> bool:
        return self.cached


class EmbeddingTrace:
    """Collects :class:`EmbeddingMeta` records for a run.

    Useful for report-level explainability: which providers/models were
    used, and how much time embedding added.
    """

    def __init__(self) -> None:
        self._records: list[EmbeddingMeta] = []

    def record(self, meta: EmbeddingMeta) -> None:
        self._records.append(meta)

    def records(self) -> list[EmbeddingMeta]:
        return list(self._records)

    def count(self) -> int:
        return len(self._records)

    def providers(self) -> list[str]:
        return sorted({r.provider for r in self._records})

    def models(self) -> list[str]:
        return sorted({r.model for r in self._records})

    def latency_stats(self) -> dict[str, float]:
        """Aggregate latency statistics over non-cached records (ms)."""
        values = [r.latency_ms for r in self._records if not r.cached]
        if not values:
            return {"count": 0, "mean_ms": 0.0, "max_ms": 0.0, "total_ms": 0.0}
        ordered = sorted(values)
        p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
        return {
            "count": len(values),
            "mean_ms": round(fmean(values), 4),
            "max_ms": round(max(values), 4),
            "p95_ms": round(p95, 4),
            "total_ms": round(sum(values), 4),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count(),
            "providers": self.providers(),
            "models": self.models(),
            "latency": self.latency_stats(),
        }

    def clear(self) -> None:
        self._records.clear()
