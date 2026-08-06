"""Dataset downloader backed by the Hugging Face datasets-server API.

Datasets published on the Hugging Face Hub are fetched over plain HTTP
from the ``/rows`` endpoint (paginated, no SDK dependency) and cached as
JSONL in a local cache directory. This is the same mechanism the existing
``scripts/build_dataset.py`` uses, factored into the benchmark package so
every dataset in the registry is downloaded through one code path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import Iterator

    from q_guardian.benchmark.registry import DatasetSpec

ROWS_API = "https://datasets-server.huggingface.co/rows"
_PAGE_SIZE = 100

_DEFAULT_CACHE_DIR = Path(
    os.environ.get("QGUARDIAN_BENCHMARK_CACHE") or str(Path.home() / ".qguardian" / "benchmark")
)


class DatasetError(RuntimeError):
    """Raised when a dataset cannot be downloaded or read."""


class DatasetDownloader:
    """Downloads benchmark datasets into a local JSONL cache.

    Args:
        cache_dir: Where downloaded splits are stored as JSONL. Defaults to
            ``$QGUARDIAN_BENCHMARK_CACHE`` or ``~/.qguardian/benchmark``.
        timeout: HTTP timeout in seconds.
        token: Hugging Face access token for gated datasets (also read from
            the ``HF_TOKEN`` environment variable).
        transport: Optional ``httpx`` transport (test seam).
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        *,
        timeout: float = 60.0,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir is not None else _DEFAULT_CACHE_DIR
        self._timeout = timeout
        self._token = token or os.environ.get("HF_TOKEN")
        self._transport = transport

    def download(self, spec: DatasetSpec) -> dict[str, Path]:
        """Download every split of ``spec`` and return ``{split: path}``.

        For Hugging Face datasets the rows are streamed through the
        datasets-server ``/rows`` API and written as JSONL under the cache
        directory (one file per split). Local formats (``jsonl`` /
        ``csv`` / ``json``) are returned in place under the spec's first
        split name.

        Raises:
            DatasetError: If the dataset is gated without a token, the
                source is unreachable, or the format is unsupported.
        """
        if spec.requires_token and not self._token:
            msg = (
                f"dataset {spec.dataset_id!r} is gated on Hugging Face: "
                "set HF_TOKEN (or pass token=...) after accepting the "
                "dataset terms on the Hub"
            )
            raise DatasetError(msg)

        if spec.format == "hf":
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            return self._download_hf(spec)
        if spec.format in ("jsonl", "csv", "json"):
            return self._load_local(spec)
        msg = f"unsupported dataset format: {spec.format!r}"
        raise DatasetError(msg)

    def _download_hf(self, spec: DatasetSpec) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        stem = spec.dataset_id.replace("/", "_")
        for split in spec.splits:
            path = self._cache_dir / f"{stem}__{split}.jsonl"
            written = 0
            with open(path, "w", encoding="utf-8") as f:
                for row in self._iter_rows(spec, split):
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    written += 1
                    if spec.max_samples is not None and written >= spec.max_samples:
                        break
            paths[split] = path
        return paths

    def _iter_rows(self, spec: DatasetSpec, split: str) -> Iterator[dict[str, Any]]:
        """Stream rows for one split from the HF datasets-server rows API."""
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        offset = 0
        with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
            while True:
                params: dict[str, Any] = {
                    "dataset": spec.source,
                    "split": split,
                    "offset": offset,
                    "length": _PAGE_SIZE,
                }
                if spec.config:
                    params["config"] = spec.config
                try:
                    response = client.get(ROWS_API, params=params, headers=headers)
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    hint = (
                        " The dataset is gated: accept its terms on the Hub "
                        "and provide an access token."
                        if exc.response.status_code == 401
                        else ""
                    )
                    msg = (
                        f"failed to download {spec.dataset_id} split {split!r}: "
                        f"HTTP {exc.response.status_code} "
                        f"({exc.response.text[:120]}){hint}"
                    )
                    raise DatasetError(msg) from exc

                payload: Any = response.json()
                rows: Any = payload.get("rows", [])
                for entry in rows:
                    row: Any = entry.get("row")
                    if isinstance(row, dict):
                        yield row
                offset += len(rows)
                total = int(payload.get("num_rows_total", 0) or 0)
                if offset >= total:
                    break

    def _load_local(self, spec: DatasetSpec) -> dict[str, Path]:
        source = Path(spec.source)
        if not source.exists():
            msg = f"local dataset not found: {source}"
            raise DatasetError(msg)
        split = spec.splits[0] if spec.splits else "default"
        return {split: source}
