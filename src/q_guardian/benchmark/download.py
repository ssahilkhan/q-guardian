"""Dataset downloader with explicit multi-source acquisition.

The downloader is the single acquisition path for every dataset in the
registry. ``DatasetSpec.source_type`` selects the routing:

* ``huggingface`` — datasets-server ``/rows`` API (paginated, no SDK
  dependency) or local ``jsonl``/``csv``/``json`` files, cached / returned
  as before.
* ``github`` — an explicit public raw artifact from
  ``raw.githubusercontent.com``, parsed by ``spec.format`` and cached as
  JSONL.
* ``direct_url`` — an explicit public ``https`` URL, parsed by
  ``spec.format`` and cached as JSONL.
* ``external`` — never auto-downloaded; raises a clear error.

Downloaded artifacts are always treated as inert data (never executed).
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from q_guardian.benchmark.registry import (
    DatasetSourceType,
    DatasetSpec,
)
from q_guardian.ml.datasets.auth import (
    AuthConfig,
    DatasetAccessType,
    DatasetAuthResolver,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

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
        auth_config: Optional AuthConfig for centralized auth management.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        *,
        timeout: float = 60.0,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
        auth_config: AuthConfig | None = None,
    ) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir is not None else _DEFAULT_CACHE_DIR
        self._timeout = timeout
        self._transport = transport

        # Use centralized auth resolver
        if auth_config is not None:
            self._auth_resolver = DatasetAuthResolver(auth_config)
        else:
            auth_cfg = AuthConfig.from_config(token)
            self._auth_resolver = DatasetAuthResolver(auth_cfg)

    @property
    def token(self) -> str | None:
        """Return the current token (never logged)."""
        return self._auth_resolver.token

    @property
    def has_token(self) -> bool:
        """Check if a token is configured."""
        return self._auth_resolver.has_token

    @property
    def auth_resolver(self) -> DatasetAuthResolver:
        """Return the auth resolver for advanced use cases."""
        return self._auth_resolver

    def download(self, spec: DatasetSpec) -> dict[str, Path]:
        """Download every split of ``spec`` and return ``{split: path}``.

        Routing depends on ``spec.source_type``:

        * ``HUGGINGFACE`` — the original behavior: ``hf`` sources stream
          rows through the datasets-server ``/rows`` API and write JSONL
          under the cache directory (one file per split); ``jsonl`` /
          ``csv`` / ``json`` sources are returned in place as local files.
        * ``GITHUB`` — fetch the explicitly identified public raw artifact
          (``https://raw.githubusercontent.com/{source}/{artifact_path}``),
          parse it by ``spec.format`` and cache it as JSONL.
        * ``DIRECT_URL`` — fetch the explicit ``https`` URL ``spec.source``,
          parse it by ``spec.format`` and cache it as JSONL.
        * ``EXTERNAL`` — never downloaded; a clear error explains that
          automatic acquisition is not supported.

        Raises:
            DatasetError: If the dataset is gated without a token, the
                source is unreachable, the URL is unsafe, or the format is
                unsupported.
        """
        access_info = self._auth_resolver.classify_access(spec)

        if access_info.access_type == DatasetAccessType.GATED:
            msg = (
                f"dataset {spec.dataset_id!r} is gated on Hugging Face: "
                "set HF_TOKEN (or pass token=...) after accepting the "
                "dataset terms on the Hub"
            )
            raise DatasetError(msg)

        if spec.source_type is DatasetSourceType.HUGGINGFACE:
            if spec.format == "hf":
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                return self._download_hf(spec)
            if spec.format in ("jsonl", "csv", "json"):
                return self._load_local(spec)
            msg = f"unsupported dataset format: {spec.format!r}"
            raise DatasetError(msg)

        if spec.source_type is DatasetSourceType.GITHUB:
            return self._download_remote(spec, self._github_artifact_url(spec))

        if spec.source_type is DatasetSourceType.DIRECT_URL:
            return self._download_remote(spec, self._validated_url(spec.source))

        if spec.source_type is DatasetSourceType.EXTERNAL:
            msg = (
                f"dataset {spec.dataset_id!r} has an external source "
                f"({spec.source!r}) that is not automatically acquired. "
                "Provision the data manually; it is not a Hugging Face dataset."
            )
            raise DatasetError(msg)

        msg = f"unsupported dataset source_type: {spec.source_type!r}"
        raise DatasetError(msg)

    def check_access(self, spec: DatasetSpec) -> DatasetAccessType:
        """Check the access type for a dataset without downloading.

        Args:
            spec: Dataset specification to check.

        Returns:
            DatasetAccessType indicating access requirements.
        """
        return self._auth_resolver.classify_access(spec).access_type

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
        headers = self._auth_resolver.get_auth_headers()
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
                    hint = ""
                    if exc.response.status_code == 401:
                        hint = (
                            " The dataset is gated: accept its terms on the Hub "
                            "and provide an access token via HF_TOKEN."
                        )
                    elif exc.response.status_code == 403:
                        hint = (
                            " Access forbidden. You may not have permission to "
                            "access this dataset even with a token."
                        )
                    elif exc.response.status_code == 404:
                        hint = " Dataset not found. Check the dataset identifier."
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

    def _github_artifact_url(self, spec: DatasetSpec) -> str:
        """Build the raw.githubusercontent.com URL for a GITHUB source.

        ``source`` must be an ``owner/repo`` id; ``artifact_path`` is the
        ``<ref>/<path>`` portion of the raw URL (the ref makes the artifact
        reproducible). The result is validated as HTTPS with no credentials.
        """
        source = spec.source.strip().strip("/")
        if "/" not in source or source.startswith(("https://", "http://")):
            msg = (
                f"github source {spec.source!r} must be an 'owner/repo' id "
                "(not a full url); the artifact is given by artifact_path"
            )
            raise DatasetError(msg)
        artifact = spec.artifact_path.strip().strip("/")
        url = f"https://raw.githubusercontent.com/{source}/{artifact}"
        return self._validated_url(url)

    def _validated_url(self, url: str) -> str:
        """Validate that ``url`` is a secure HTTPS location.

        Accepts only ``https`` URLs with a host and no embedded credentials.
        Redirect-free by default (''htps`` failures surface as errors).
        """
        raw = url.strip()
        try:
            parts = urlsplit(raw)
        except ValueError as exc:
            msg = f"invalid url {raw!r}: {exc}"
            raise DatasetError(msg) from exc
        if parts.scheme != "https":
            msg = f"only https URLs are supported for remote sources, got {raw!r}"
            raise DatasetError(msg)
        if not parts.netloc or not parts.path:
            msg = f"remote source url must include a host and a path: {raw!r}"
            raise DatasetError(msg)
        if parts.username is not None or parts.password is not None:
            msg = f"remote source url must not embed credentials: {raw!r}"
            raise DatasetError(msg)
        return raw

    def _download_remote(self, spec: DatasetSpec, url: str) -> dict[str, Path]:
        """Fetch a public remote artifact, parse it, and cache it as JSONL.

        The artifact is always treated as inert data: it is downloaded over
        HTTPS, parsed by ``spec.format`` (csv/json/jsonl) and written as
        JSONL rows under the cache directory, never executed.
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        split = spec.splits[0] if spec.splits else "default"
        stem = spec.dataset_id.replace("/", "_")
        path = self._cache_dir / f"{stem}__{split}.jsonl"
        with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
            response = client.get(url)
            if response.status_code != 200:
                hint = ""
                if response.status_code == 404:
                    hint = " Artifact not found. Check the URL and the artifact_path/ref."
                elif response.status_code in (401, 403):
                    hint = " Access forbidden. This artifact may require provider credentials."
                msg = (
                    f"failed to download {spec.dataset_id}: "
                    f"HTTP {response.status_code} ({response.text[:120]}){hint}"
                )
                raise DatasetError(msg)
            text = response.text

        written = 0
        with open(path, "w", encoding="utf-8") as f:
            for row in self._parse_remote_rows(spec, text):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1
                if spec.max_samples is not None and written >= spec.max_samples:
                    break
        return {split: path}

    def _parse_remote_rows(self, spec: DatasetSpec, text: str) -> Iterator[dict[str, Any]]:
        """Parse raw artifact content into JSON-object rows.

        Non-object rows are skipped so the rest of the pipeline (validation,
        normalization) keeps receiving JSONL objects only.
        """
        if spec.format == "csv":
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                if isinstance(row, dict):
                    yield dict(row)
            return
        if spec.format == "json":
            data: Any = json.loads(text)
            raw_rows = data if isinstance(data, list) else data.get("data", data.get("entries"))
            if not isinstance(raw_rows, list):
                return
            for row in raw_rows:
                if isinstance(row, dict):
                    yield row
            return
        if spec.format == "jsonl":
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row
            return
        msg = f"unsupported remote dataset format: {spec.format!r}"
        raise DatasetError(msg)

    def _load_local(self, spec: DatasetSpec) -> dict[str, Path]:
        source = Path(spec.source)
        if not source.exists():
            msg = f"local dataset not found: {source}"
            raise DatasetError(msg)
        split = spec.splits[0] if spec.splits else "default"
        return {split: source}
