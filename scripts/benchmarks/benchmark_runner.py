from __future__ import annotations

import json
import math
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BenchmarkResult:
    name: str
    iterations: int
    min_ns: int
    max_ns: int
    avg_ns: float
    p50_ns: float
    p95_ns: float
    p99_ns: float
    total_ns: int
    std_dev_ns: float = 0.0
    ops_per_sec: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def min_us(self) -> float:
        return self.min_ns / 1_000

    @property
    def avg_us(self) -> float:
        return self.avg_ns / 1_000

    @property
    def p50_us(self) -> float:
        return self.p50_ns / 1_000

    @property
    def p95_us(self) -> float:
        return self.p95_ns / 1_000

    @property
    def p99_us(self) -> float:
        return self.p99_ns / 1_000

    @property
    def max_us(self) -> float:
        return self.max_ns / 1_000

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["min_us"] = self.min_us
        d["avg_us"] = self.avg_us
        d["p50_us"] = self.p50_us
        d["p95_us"] = self.p95_us
        d["p99_us"] = self.p99_us
        d["max_us"] = self.max_us
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def summary_line(self) -> str:
        return (
            f"{self.name:<45} "
            f"n={self.iterations:<6} "
            f"min={self.min_us:>10.1f}us  "
            f"avg={self.avg_us:>10.1f}us  "
            f"p50={self.p50_us:>10.1f}us  "
            f"p95={self.p95_us:>10.1f}us  "
            f"p99={self.p99_us:>10.1f}us  "
            f"max={self.max_us:>10.1f}us  "
            f"ops/s={self.ops_per_sec:>10.0f}"
        )


def compute_stats(
    latencies_ns: list[int], name: str, iterations: int, metadata: dict[str, Any] | None = None
) -> BenchmarkResult:
    sorted_lat = sorted(latencies_ns)
    total = sum(sorted_lat)
    avg = total / len(sorted_lat) if sorted_lat else 0.0
    sd = statistics.stdev(sorted_lat) if len(sorted_lat) >= 2 else 0.0

    p50 = _percentile(sorted_lat, 50)
    p95 = _percentile(sorted_lat, 95)
    p99 = _percentile(sorted_lat, 99)

    ops_per_sec = (iterations / (total / 1_000_000_000)) if total > 0 else 0.0

    return BenchmarkResult(
        name=name,
        iterations=iterations,
        min_ns=sorted_lat[0] if sorted_lat else 0,
        max_ns=sorted_lat[-1] if sorted_lat else 0,
        avg_ns=avg,
        p50_ns=p50,
        p95_ns=p95,
        p99_ns=p99,
        total_ns=total,
        std_dev_ns=sd,
        ops_per_sec=ops_per_sec,
        metadata=metadata or {},
    )


def _percentile(sorted_data: list[int], pct: float) -> float:
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_data[int(k)])
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


def benchmark(
    func: Callable[..., Any],
    iterations: int = 100,
    warmup: int = 10,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> BenchmarkResult:
    bench_name = name or func.__qualname__

    for _ in range(warmup):
        func()

    latencies: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        func()
        end = time.perf_counter_ns()
        latencies.append(end - start)

    return compute_stats(latencies, bench_name, iterations, metadata)


async def async_benchmark(
    func: Callable[..., Any],
    iterations: int = 100,
    warmup: int = 10,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> BenchmarkResult:
    bench_name = name or func.__qualname__

    for _ in range(warmup):
        await func()

    latencies: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        await func()
        end = time.perf_counter_ns()
        latencies.append(end - start)

    return compute_stats(latencies, bench_name, iterations, metadata)


class BenchmarkSuite:
    def __init__(self, name: str = "suite") -> None:
        self.name = name
        self._results: list[BenchmarkResult] = []
        self._context: dict[str, Any] = {}

    def __enter__(self) -> BenchmarkSuite:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def add(self, result: BenchmarkResult) -> None:
        self._results.append(result)

    @property
    def results(self) -> list[BenchmarkResult]:
        return list(self._results)

    def to_json(self) -> str:
        return json.dumps(
            {
                "suite": self.name,
                "results": [r.to_dict() for r in self._results],
            },
            indent=2,
        )

    def print_table(self) -> None:
        sep = "=" * 180
        print(f"\n{sep}")
        print(f"  Benchmark Suite: {self.name}")
        print(sep)
        header = (
            f"{'Benchmark':<45} "
            f"{'Iterations':<10} "
            f"{'Min (us)':>10}  "
            f"{'Avg (us)':>10}  "
            f"{'P50 (us)':>10}  "
            f"{'P95 (us)':>10}  "
            f"{'P99 (us)':>10}  "
            f"{'Max (us)':>10}  "
            f"{'Ops/s':>10}"
        )
        print(header)
        print("-" * 180)
        for r in self._results:
            print(r.summary_line())
        print(sep)

    def save_json(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")
        return p

    def compare_with(self, baseline: BenchmarkSuite) -> list[dict[str, Any]]:
        baseline_map = {r.name: r for r in baseline._results}
        comparisons: list[dict[str, Any]] = []
        for r in self._results:
            b = baseline_map.get(r.name)
            if b is None:
                comparisons.append({"name": r.name, "status": "new"})
                continue
            avg_delta = ((r.avg_ns - b.avg_ns) / b.avg_ns * 100) if b.avg_ns > 0 else 0.0
            p95_delta = ((r.p95_ns - b.p95_ns) / b.p95_ns * 100) if b.p95_ns > 0 else 0.0
            comparisons.append(
                {
                    "name": r.name,
                    "baseline_avg_us": b.avg_us,
                    "current_avg_us": r.avg_us,
                    "avg_delta_pct": round(avg_delta, 2),
                    "baseline_p95_us": b.p95_us,
                    "current_p95_us": r.p95_us,
                    "p95_delta_pct": round(p95_delta, 2),
                    "regression": avg_delta > 10.0,
                }
            )
        return comparisons

    @classmethod
    def load_json(cls, path: str | Path) -> BenchmarkSuite:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        suite = cls(name=data.get("suite", "loaded"))
        for rd in data.get("results", []):
            suite._results.append(
                BenchmarkResult(
                    **{k: v for k, v in rd.items() if k in BenchmarkResult.__dataclass_fields__}
                )
            )
        return suite


if __name__ == "__main__":

    def _noop() -> None:
        pass

    suite = BenchmarkSuite(name="runner-smoke-test")
    suite.add(benchmark(_noop, iterations=1000, warmup=100, name="noop-baseline"))
    suite.print_table()
    suite.save_json("scripts/benchmarks/_runner_smoke.json")
    print("\nSaved to scripts/benchmarks/_runner_smoke.json")
