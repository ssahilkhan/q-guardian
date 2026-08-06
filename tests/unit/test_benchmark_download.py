"""Unit tests for the dataset downloader."""

from __future__ import annotations

import json

import httpx
import pytest

from q_guardian.benchmark.download import DatasetDownloader, DatasetError
from q_guardian.benchmark.registry import DatasetSpec


def _hf_spec(**kwargs) -> DatasetSpec:
    fields = {
        "dataset_id": "fake/rows",
        "name": "Fake Rows",
        "source": "fake/rows",
        "format": "hf",
        "config": "default",
        "splits": ("train",),
        "text_fields": ("text",),
        "label_field": "label",
        "license": "MIT",
    }
    fields.update(kwargs)
    return DatasetSpec(**fields)


def _read_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


class TestDownloaderHf:
    def test_paginates_and_caches_jsonl(self, tmp_path):
        def handler(request):
            offset = int(request.url.params["offset"])
            rows = [{"row": {"text": f"sample {i}", "label": 0}} for i in range(offset, offset + 3)]
            return httpx.Response(200, json={"rows": rows, "num_rows_total": 6})

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        paths = downloader.download(_hf_spec(max_samples=5))

        assert set(paths) == {"train"}
        lines = [json.loads(line) for line in _read_lines(paths["train"])]
        assert len(lines) == 5
        assert lines[0]["text"] == "sample 0"

    def test_respects_max_samples(self, tmp_path):
        def handler(request):
            offset = int(request.url.params["offset"])
            rows = [{"row": {"text": f"sample {offset + i}", "label": 0}} for i in range(2)]
            return httpx.Response(200, json={"rows": rows, "num_rows_total": 1000})

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        paths = downloader.download(_hf_spec(max_samples=3))

        assert len(_read_lines(paths["train"])) == 3

    def test_multiple_splits(self, tmp_path):
        def handler(request):
            split = request.url.params["split"]
            rows = [{"row": {"text": f"{split} row", "label": 0}}]
            return httpx.Response(200, json={"rows": rows, "num_rows_total": 1})

        spec = _hf_spec(splits=("train", "test"))
        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        paths = downloader.download(spec)

        assert set(paths) == {"train", "test"}
        assert json.loads(_read_lines(paths["train"])[0])["text"] == "train row"
        assert json.loads(_read_lines(paths["test"])[0])["text"] == "test row"

    def test_gated_without_token_raises(self, tmp_path):
        downloader = DatasetDownloader(tmp_path)
        with pytest.raises(DatasetError, match="gated"):
            downloader.download(_hf_spec(requires_token=True))

    def test_gated_with_token_attempts_download(self, tmp_path):
        def handler(request):
            assert "Authorization" in request.headers
            return httpx.Response(200, json={"rows": [], "num_rows_total": 0})

        downloader = DatasetDownloader(
            tmp_path, token="hf_test", transport=httpx.MockTransport(handler)
        )
        paths = downloader.download(_hf_spec(requires_token=True))
        assert paths["train"].exists()

    def test_http_error_raises_dataset_error(self, tmp_path):
        def handler(_request):
            return httpx.Response(404, text="not found")

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        with pytest.raises(DatasetError, match="HTTP 404"):
            downloader.download(_hf_spec())


class TestDownloaderLocal:
    def test_local_jsonl_returned_in_place(self, tmp_path):
        source = tmp_path / "local.jsonl"
        source.write_text('{"text": "a", "label": 0}\n', encoding="utf-8")
        spec = DatasetSpec(
            dataset_id="local",
            name="Local",
            source=str(source),
            format="jsonl",
            splits=("default",),
            text_fields=("text",),
            label_field="label",
        )
        downloader = DatasetDownloader(tmp_path / "cache")
        paths = downloader.download(spec)

        assert paths == {"default": source}

    def test_missing_local_raises(self, tmp_path):
        spec = DatasetSpec(
            dataset_id="local",
            name="Local",
            source=str(tmp_path / "nope.jsonl"),
            format="jsonl",
        )
        downloader = DatasetDownloader(tmp_path)
        with pytest.raises(DatasetError, match="not found"):
            downloader.download(spec)

    def test_unsupported_format_raises(self, tmp_path):
        spec = DatasetSpec(dataset_id="bad", name="Bad", source="x", format="parquet")
        downloader = DatasetDownloader(tmp_path)
        with pytest.raises(DatasetError, match="unsupported"):
            downloader.download(spec)
