"""Tests for the DatasetDownloader with authentication integration."""

from __future__ import annotations

import httpx
import pytest

from q_guardian.benchmark.download import DatasetDownloader, DatasetError
from q_guardian.benchmark.registry import DatasetSpec
from q_guardian.ml.datasets.auth import DatasetAccessType


def _public_spec(**kwargs) -> DatasetSpec:
    fields = {
        "dataset_id": "public-dataset",
        "name": "Public Dataset",
        "source": "org/public-dataset",
        "format": "hf",
        "config": "default",
        "splits": ("train",),
        "text_fields": ("text",),
        "label_field": "label",
        "license": "MIT",
        "requires_token": False,
    }
    fields.update(kwargs)
    return DatasetSpec(**fields)


def _gated_spec(**kwargs) -> DatasetSpec:
    fields = {
        "dataset_id": "gated-dataset",
        "name": "Gated Dataset",
        "source": "org/gated-dataset",
        "format": "hf",
        "config": "default",
        "splits": ("train",),
        "text_fields": ("text",),
        "label_field": "label",
        "license": "MIT",
        "requires_token": True,
        "homepage": "https://huggingface.co/datasets/org/gated-dataset",
    }
    fields.update(kwargs)
    return DatasetSpec(**fields)


class TestDownloaderAuthIntegration:
    def test_downloader_with_auth_config(self, tmp_path):
        from q_guardian.ml.datasets.auth import AuthConfig

        auth_config = AuthConfig(hf_token="hf_test_token")
        downloader = DatasetDownloader(tmp_path, auth_config=auth_config)
        assert downloader.has_token is True
        assert downloader.token == "hf_test_token"

    def test_downloader_with_explicit_token(self, tmp_path):
        downloader = DatasetDownloader(tmp_path, token="hf_explicit_token")
        assert downloader.has_token is True
        assert downloader.token == "hf_explicit_token"

    def test_downloader_without_token(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        downloader = DatasetDownloader(tmp_path)
        assert downloader.has_token is False
        assert downloader.token is None

    def test_check_access_public(self, tmp_path):
        downloader = DatasetDownloader(tmp_path)
        spec = _public_spec()
        access_type = downloader.check_access(spec)
        assert access_type == DatasetAccessType.PUBLIC

    def test_check_access_gated_without_token(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        downloader = DatasetDownloader(tmp_path)
        spec = _gated_spec()
        access_type = downloader.check_access(spec)
        assert access_type == DatasetAccessType.GATED

    def test_check_access_gated_with_token(self, tmp_path):
        downloader = DatasetDownloader(tmp_path, token="hf_test_token")
        spec = _gated_spec()
        access_type = downloader.check_access(spec)
        assert access_type == DatasetAccessType.AUTHENTICATED

    def test_download_gated_without_token_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        downloader = DatasetDownloader(tmp_path)
        spec = _gated_spec()
        with pytest.raises(DatasetError, match="gated"):
            downloader.download(spec)

    def test_download_public_without_token_works(self, tmp_path):
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "rows": [{"row": {"text": "sample", "label": 0}}],
                    "num_rows_total": 1,
                },
            )

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        spec = _public_spec()
        paths = downloader.download(spec)
        assert "train" in paths

    def test_download_gated_with_token_works(self, tmp_path):
        def handler(request):
            assert "Authorization" in request.headers
            assert request.headers["Authorization"] == "Bearer hf_test_token"
            return httpx.Response(
                200,
                json={
                    "rows": [{"row": {"text": "sample", "label": 0}}],
                    "num_rows_total": 1,
                },
            )

        downloader = DatasetDownloader(tmp_path, token="hf_test_token", transport=httpx.MockTransport(handler))
        spec = _gated_spec()
        paths = downloader.download(spec)
        assert "train" in paths

    def test_auth_resolver_accessible(self, tmp_path):
        downloader = DatasetDownloader(tmp_path, token="hf_test_token")
        resolver = downloader.auth_resolver
        assert resolver.has_token is True
        assert resolver.token == "hf_test_token"

    def test_403_error_message(self, tmp_path):
        def handler(request):
            return httpx.Response(403, text="Forbidden")

        downloader = DatasetDownloader(tmp_path, token="hf_test_token", transport=httpx.MockTransport(handler))
        spec = _gated_spec()
        with pytest.raises(DatasetError, match="forbidden|permission|access denied"):
            downloader.download(spec)

    def test_404_error_message(self, tmp_path):
        def handler(request):
            return httpx.Response(404, text="Not found")

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        spec = _public_spec()
        with pytest.raises(DatasetError, match="not found|404"):
            downloader.download(spec)

    def test_401_error_message_without_token(self, tmp_path):
        def handler(request):
            return httpx.Response(401, text="Unauthorized")

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        spec = _gated_spec()
        with pytest.raises(DatasetError, match="gated|unauthorized|401"):
            downloader.download(spec)

    def test_local_dataset_no_auth_needed(self, tmp_path):
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
        downloader = DatasetDownloader(tmp_path)
        paths = downloader.download(spec)
        assert paths == {"default": source}

    def test_token_in_headers_not_logged(self, tmp_path, caplog):
        """Ensure token is not exposed in logs."""
        import logging

        caplog.set_level(logging.DEBUG)

        def handler(request):
            return httpx.Response(
                200,
                json={"rows": [{"row": {"text": "sample", "label": 0}}], "num_rows_total": 1},
            )

        downloader = DatasetDownloader(tmp_path, token="hf_secret_token_12345", transport=httpx.MockTransport(handler))
        spec = _gated_spec()
        downloader.download(spec)

        # Check that token doesn't appear in logs
        log_text = caplog.text
        assert "hf_secret_token_12345" not in log_text
        assert "Bearer" not in log_text or "hf_secret_token_12345" not in log_text