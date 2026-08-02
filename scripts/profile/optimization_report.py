"""Optimization recommendations based on memory profiler results.

Analyses profiler data and produces a markdown report with actionable
suggestions for reducing memory usage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    """Single optimization finding."""

    category: str
    severity: str  # "info", "warning", "critical"
    title: str
    description: str
    recommendation: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "details": self.details,
        }

    def to_markdown(self) -> str:
        icon = {"info": "[INFO]", "warning": "[WARN]", "critical": "[CRIT]"}.get(self.severity, "[•]")
        lines = [
            f"### {icon} [{self.severity.upper()}] {self.title}",
            "",
            self.description,
            "",
            f"**Recommendation:** {self.recommendation}",
        ]
        if self.details:
            lines.append("")
            lines.append("<details>")
            lines.append("<summary>Details</summary>")
            lines.append("")
            for k, v in self.details.items():
                lines.append(f"- **{k}:** {v}")
            lines.append("</details>")
        return "\n".join(lines)


class OptimizationReport:
    """Analyse profiler results and generate optimization recommendations."""

    def __init__(self, profiler_report: dict[str, Any]) -> None:
        self._report = profiler_report
        self._findings: list[Finding] = []
        self._analyse()

    def _analyse(self) -> None:
        self._check_large_allocations()
        self._check_gc_pressure()
        self._check_memory_growth()
        self._check_object_count()

    def _check_large_allocations(self) -> None:
        allocs = self._report.get("top_allocations", [])
        large = [a for a in allocs if a.get("size_mb", 0) >= 1.0]
        if not large:
            return

        top = large[0]
        self._findings.append(
            Finding(
                category="allocations",
                severity="warning" if top.get("size_mb", 0) < 10 else "critical",
                title="Large Memory Allocations Detected",
                description=(
                    f"Found {len(large)} allocation(s) exceeding 1 MB. "
                    f"Largest is {top.get('size_mb', 0):.2f} MB at "
                    f"{top.get('filename', '?')}:{top.get('lineno', '?')}."
                ),
                recommendation=(
                    "Consider object pooling for frequently allocated large objects, "
                    "lazy loading to defer allocation until needed, or streaming "
                    "approaches to avoid holding large data in memory at once."
                ),
                details={
                    "count": len(large),
                    "top_location": f"{top.get('filename', '?')}:{top.get('lineno', '?')}",
                    "top_size_mb": top.get("size_mb", 0),
                },
            )
        )

    def _check_gc_pressure(self) -> None:
        gc_stats = self._report.get("gc_statistics", {})
        total = gc_stats.get("total_collections", 0)
        by_gen = gc_stats.get("by_generation", {})
        gen0 = by_gen.get("gen0", 0)
        snap_count = gc_stats.get("snapshot_count", 1)

        collections_per_snapshot = total / snap_count if snap_count > 0 else 0

        if collections_per_snapshot > 5:
            self._findings.append(
                Finding(
                    category="gc",
                    severity="warning",
                    title="Frequent Garbage Collection",
                    description=(
                        f"Averaging {collections_per_snapshot:.1f} GC collections per snapshot "
                        f"(gen0: {gen0}, total: {total})."
                    ),
                    recommendation=(
                        "Reduce object churn by reusing objects where possible. "
                        "Consider using object pools, __slots__ on classes, "
                        "or dataclasses with slots=True to reduce per-instance overhead."
                    ),
                    details={
                        "total_collections": total,
                        "gen0_collections": gen0,
                        "per_snapshot": round(collections_per_snapshot, 2),
                    },
                )
            )

    def _check_memory_growth(self) -> None:
        leak = self._report.get("leak_analysis", {})
        if not leak.get("leak_suspected", False):
            return

        heap_slope = leak.get("heap_slope_mb_per_sec", 0)
        obj_slope = leak.get("object_slope_per_sec", 0)

        severity = "critical" if heap_slope > 1.0 else "warning"
        self._findings.append(
            Finding(
                category="leaks",
                severity=severity,
                title="Potential Memory Leak Detected",
                description=(
                    f"Heap growing at {heap_slope:.4f} MB/s "
                    f"({obj_slope:.1f} objects/s) over "
                    f"{leak.get('time_span_sec', 0):.1f}s."
                ),
                recommendation=(
                    "Investigate growing object counts for objects that should be "
                    "released. Use weakref for caches, ensure proper cleanup in "
                    "__del__ or context managers, and check for circular references "
                    "preventing garbage collection."
                ),
                details={
                    "heap_growth_mb": leak.get("heap_growth_mb", 0),
                    "heap_slope_mb_per_sec": heap_slope,
                    "object_growth": leak.get("object_growth", 0),
                    "time_span_sec": leak.get("time_span_sec", 0),
                },
            )
        )

    def _check_object_count(self) -> None:
        summary = self._report.get("summary", {})
        start = summary.get("start_objects", 0)
        end = summary.get("end_objects", 0)
        if start == 0:
            return

        growth_pct = ((end - start) / start * 100) if start > 0 else 0

        if growth_pct > 20:
            self._findings.append(
                Finding(
                    category="objects",
                    severity="warning" if growth_pct < 100 else "critical",
                    title="High Object Count Growth",
                    description=(
                        f"Object count grew from {start:,} to {end:,} "
                        f"({growth_pct:+.1f}%)."
                    ),
                    recommendation=(
                        "High object counts increase GC overhead. Consider using "
                        "__slots__ or dataclass(slots=True) to reduce per-object "
                        "memory, named tuples for simple data containers, or "
                        "array/module-level storage for fixed datasets."
                    ),
                    details={
                        "start_count": start,
                        "end_count": end,
                        "growth_pct": round(growth_pct, 2),
                    },
                )
            )

    @property
    def findings(self) -> list[Finding]:
        return list(self._findings)

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {"info": 0, "warning": 0, "critical": 0}
        for f in self._findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts

    def to_markdown(self) -> str:
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        counts = self.summary

        lines = [
            "# Q-Guardian Memory Optimization Report",
            "",
            f"*Generated: {ts}*",
            "",
            "## Summary",
            "",
            f"| Severity | Count |",
            f"|----------|-------|",
            f"| Critical | {counts['critical']} |",
            f"| Warning  | {counts['warning']} |",
            f"| Info     | {counts['info']} |",
            f"| **Total** | **{len(self._findings)}** |",
            "",
        ]

        if not self._findings:
            lines.append("No optimization issues detected. Memory usage appears healthy.")
            return "\n".join(lines)

        lines.append("## Findings")
        lines.append("")

        for i, finding in enumerate(self._findings, 1):
            lines.append(f"## {i}. {finding.title}")
            lines.append("")
            lines.append(finding.to_markdown())
            lines.append("")
            lines.append("---")
            lines.append("")

        lines.append("## General Guidelines")
        lines.append("")
        lines.append("1. **Object Pooling:** Reuse large or frequently allocated objects")
        lines.append("2. **Lazy Loading:** Defer allocation until data is actually needed")
        lines.append("3. **__slots__:** Reduce per-instance memory on data-heavy classes")
        lines.append("4. **Weak References:** Use `weakref` for caches to allow GC cleanup")
        lines.append("5. **Streaming:** Process large datasets in chunks rather than loading all at once")
        lines.append("6. **Context Managers:** Ensure resources are released deterministically")

        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "summary": self.summary,
                "findings": [f.to_dict() for f in self._findings],
            },
            indent=2,
        )

    def save(self, path: str | Path, fmt: str = "markdown") -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            p.write_text(self.to_json(), encoding="utf-8")
        else:
            p.write_text(self.to_markdown(), encoding="utf-8")
        return p


if __name__ == "__main__":
    import time

    from scripts.profile.memory_profiler import MemoryProfiler

    print("Running quick profiler snapshot for report generation...")
    profiler = MemoryProfiler(interval=0.5)
    profiler.start()
    _ = [bytearray(2048) for _ in range(200)]
    time.sleep(2)
    profiler.stop()
    report = profiler.generate_report()

    opt = OptimizationReport(report)
    print(opt.to_markdown())
    print(f"\nJSON output:")
    print(opt.to_json())
