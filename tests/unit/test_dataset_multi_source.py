"""Tests for the minimal multi-source dataset foundation.

Covers the strict ``DatasetSourceType`` model, the ``DatasetSpec``
physical-location contract, downloader routing, remote format parsing,
and the security constraints on external acquisition.
"""

from __future__ import annotations

import json

import httpx
import pytest

from q_guardian.benchmark.download import DatasetDownloader, DatasetError
from q_guardian.benchmark.registry import DatasetSourceType, DatasetSpec
from q_guardian.training.normalize import DatasetRecordPreprocessor
from q_guardian.training.schema import GENERIC_MALICIOUS_CATEGORY


def _spec(**kwargs) -> DatasetSpec:
    fields = {
        "dataset_id": "advbench",
        "name": "AdvBench",
        "source": "llm-attacks/llm-attacks",
        "format": "csv",
        "splits": ("train",),
        "text_fields": ("goal",),
        "label_field": "target",
        "source_type": "github",
        "artifact_path": "main/data/advbench/harmful_behaviors.csv",
    }
    fields.update(kwargs)
    return DatasetSpec(**fields)


def _read_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


class TestSourceTypeModel:
    def test_defaults_to_huggingface(self):
        spec = DatasetSpec(dataset_id="d", name="D", source="owner/repo", format="hf")
        assert spec.source_type is DatasetSourceType.HUGGINGFACE
        assert spec.artifact_path == ""

    def test_string_source_type_is_coerced(self):
        spec = _spec()
        assert spec.source_type is DatasetSourceType.GITHUB

    def test_invalid_source_type_string_rejected(self):
        with pytest.raises(ValueError, match="invalid dataset source_type"):
            DatasetSpec(dataset_id="d", name="D", source="x", source_type="ftp")

    def test_invalid_source_type_value_rejected(self):
        with pytest.raises(ValueError, match="invalid dataset source_type"):
            DatasetSpec(dataset_id="d", name="D", source="x", source_type=123)

    def test_github_requires_artifact_path(self):
        with pytest.raises(ValueError, match="artifact_path"):
            _spec(artifact_path="")

    def test_direct_url_forbids_artifact_path(self):
        with pytest.raises(ValueError, match="only valid for github sources"):
            _spec(
                source_type="direct_url",
                source="https://example.com/files/data.json",
                artifact_path="x.csv",
            )

    def test_huggingface_forbids_artifact_path(self):
        with pytest.raises(ValueError, match="only valid for github sources"):
            _spec(source_type="huggingface", artifact_path="x.csv")

    def test_to_dict_exposes_source_type_as_string(self):
        data = _spec().to_dict()
        assert data["source_type"] == "github"


class TestHuggingFaceBehaviorPreserved:
    def test_hf_format_still_hits_datasets_server(self, tmp_path):
        def handler(request):
            assert "datasets-server.huggingface.co/rows" in str(request.url)
            return httpx.Response(
                200, json={"rows": [{"row": {"text": "t", "label": 0}}], "num_rows_total": 1}
            )

        spec = DatasetSpec(
            dataset_id="fake/rows",
            name="Fake Rows",
            source="fake/rows",
            format="hf",
            splits=("train",),
            text_fields=("text",),
            label_field="label",
        )
        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        paths = downloader.download(spec)
        assert json.loads(_read_lines(paths["train"])[0])["text"] == "t"

    def test_local_jsonl_unchanged(self, tmp_path):
        source = tmp_path / "local.jsonl"
        source.write_text('{"text": "a", "label": 0}\n', encoding="utf-8")
        spec = DatasetSpec(
            dataset_id="local",
            name="Local",
            source=str(source),
            format="jsonl",
            splits=("default",),
        )
        paths = DatasetDownloader(tmp_path / "cache").download(spec)
        assert paths == {"default": source}


class TestGithubRouting:
    def test_fetches_raw_artifact_and_caches_jsonl(self, tmp_path):
        def handler(request):
            assert str(request.url) == (
                "https://raw.githubusercontent.com/llm-attacks/llm-attacks/"
                "main/data/advbench/harmful_behaviors.csv"
            )
            return httpx.Response(200, text="goal,target\nharmful 1,ok\nharmful 2,no\n")

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        paths = downloader.download(_spec())

        assert set(paths) == {"train"}
        lines = [json.loads(line) for line in _read_lines(paths["train"])]
        assert len(lines) == 2
        assert lines[0] == {"goal": "harmful 1", "target": "ok"}

    def test_send_no_authorization_header(self, tmp_path):
        def handler(request):
            assert "Authorization" not in request.headers
            return httpx.Response(200, text="goal,target\nx,y\n")

        downloader = DatasetDownloader(
            tmp_path, token="hf_test", transport=httpx.MockTransport(handler)
        )
        downloader.download(_spec())

    def test_github_source_must_be_owner_repo(self, tmp_path):
        downloader = DatasetDownloader(
            tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(200))
        )
        with pytest.raises(DatasetError, match="owner/repo"):
            downloader.download(_spec(source="https://github.com/x/y"))

    def test_max_samples_honored(self, tmp_path):
        def handler(_request):
            return httpx.Response(200, text="goal,target\na,1\nb,2\nc,3\n")

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        paths = downloader.download(_spec(max_samples=2))
        assert len(_read_lines(paths["train"])) == 2


class TestDirectUrlRouting:
    def test_fetches_explicit_url(self, tmp_path):
        def handler(request):
            assert str(request.url) == "https://example.com/files/attacks.json"
            return httpx.Response(200, json={"data": [{"text": "hi", "label": 1}]})

        spec = DatasetSpec(
            dataset_id="direct",
            name="Direct",
            source="https://example.com/files/attacks.json",
            format="json",
            splits=("train",),
            text_fields=("text",),
            label_field="label",
            source_type="direct_url",
        )
        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        paths = downloader.download(spec)
        assert json.loads(_read_lines(paths["train"])[0])["text"] == "hi"


class TestExternalSource:
    def test_raises_without_downloading(self, tmp_path):
        spec = _spec(source_type="external", source="some-external-catalog", artifact_path="")
        downloader = DatasetDownloader(
            tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(200))
        )
        with pytest.raises(DatasetError, match="external source"):
            downloader.download(spec)
        assert not any(tmp_path.iterdir())


class TestRemoteFormats:
    def test_json_entries_key(self, tmp_path):
        def handler(_request):
            return httpx.Response(200, json={"entries": [{"text": "a", "label": 0}]})

        spec = DatasetSpec(
            dataset_id="e",
            name="E",
            source="https://x.com/data.json",
            format="json",
            source_type="direct_url",
        )
        paths = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler)).download(spec)
        assert json.loads(_read_lines(paths["default"])[0])["text"] == "a"

    def test_json_top_level_list(self, tmp_path):
        def handler(_request):
            return httpx.Response(200, json=[{"text": "a", "label": 1}])

        spec = DatasetSpec(
            dataset_id="l",
            name="L",
            source="https://x.com/data.json",
            format="json",
            source_type="direct_url",
        )
        paths = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler)).download(spec)
        assert len(_read_lines(paths["default"])) == 1

    def test_jsonl_skips_blank_and_invalid_lines(self, tmp_path):
        def handler(_request):
            return httpx.Response(
                200, text='{"text": "ok", "label": 0}\n\nnot json\n{"text": "ok2", "label": 1}\n'
            )

        spec = DatasetSpec(
            dataset_id="j",
            name="J",
            source="https://x.com/data.jsonl",
            format="jsonl",
            source_type="direct_url",
            max_samples=10,
        )
        paths = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler)).download(spec)
        lines = [json.loads(line) for line in _read_lines(paths["default"])]
        assert [r["text"] for r in lines] == ["ok", "ok2"]

    def test_unsupported_remote_format_raises(self, tmp_path):
        spec = DatasetSpec(
            dataset_id="p",
            name="P",
            source="https://x.com/data.parquet",
            format="parquet",
            source_type="direct_url",
        )
        downloader = DatasetDownloader(
            tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(200))
        )
        with pytest.raises(DatasetError, match="parquet"):
            downloader.download(spec)


class TestRemoteSecurity:
    def test_rejects_http_url(self, tmp_path):
        spec = DatasetSpec(
            dataset_id="h",
            name="H",
            source="http://x.com/data.json",
            format="json",
            source_type="direct_url",
        )
        downloader = DatasetDownloader(
            tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(200))
        )
        with pytest.raises(DatasetError, match="https"):
            downloader.download(spec)

    def test_rejects_credentials_in_url(self, tmp_path):
        spec = DatasetSpec(
            dataset_id="c",
            name="C",
            source="https://user:secret@example.com/data.json",
            format="json",
            source_type="direct_url",
        )
        downloader = DatasetDownloader(
            tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(200))
        )
        with pytest.raises(DatasetError, match="credentials"):
            downloader.download(spec)

    def test_non_200_raises_with_status(self, tmp_path):
        def handler(_request):
            return httpx.Response(404, text="nope")

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        with pytest.raises(DatasetError, match="HTTP 404"):
            downloader.download(_spec())

    def test_not_found_hint(self, tmp_path):
        def handler(_request):
            return httpx.Response(404, text="nope")

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        with pytest.raises(DatasetError, match="Artifact not found"):
            downloader.download(_spec())

    def test_forbidden_hint(self, tmp_path):
        def handler(_request):
            return httpx.Response(403, text="nope")

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        with pytest.raises(DatasetError, match="Access forbidden"):
            downloader.download(_spec())


class TestAdvBenchMigration:
    """Regression coverage for the migrated ``advbench`` registry spec."""

    def _advbench_spec(self, **kwargs) -> DatasetSpec:
        fields = {
            "dataset_id": "advbench",
            "name": "AdvBench (official GitHub)",
            "source": "llm-attacks/llm-attacks",
            "format": "csv",
            "splits": ("default",),
            "text_fields": ("goal",),
            "label_field": None,
            "default_label": 1,
            "license": "MIT",
            "homepage": "https://github.com/llm-attacks/llm-attacks",
            "requires_token": False,
            "source_type": DatasetSourceType.GITHUB,
            "artifact_path": (
                "a62d1307e38b3a076e614b20781c785fd860d813/data/advbench/harmful_behaviors.csv"
            ),
        }
        fields.update(kwargs)
        return DatasetSpec(**fields)

    def test_constructs_pinned_github_url(self, tmp_path):
        seen: list[str] = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(200, text='goal,target\nbehavior 1,"Sure, here is 1"\n')

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        paths = downloader.download(self._advbench_spec())

        assert seen == [
            "https://raw.githubusercontent.com/llm-attacks/llm-attacks/"
            "a62d1307e38b3a076e614b20781c785fd860d813/data/advbench/harmful_behaviors.csv"
        ]
        assert json.loads(_read_lines(paths["default"])[0]) == {
            "goal": "behavior 1",
            "target": "Sure, here is 1",
        }

    def test_sends_no_authorization_header(self, tmp_path):
        def handler(request):
            assert "Authorization" not in request.headers
            return httpx.Response(200, text="goal,target\nx,y\n")

        downloader = DatasetDownloader(
            tmp_path, token="hf_test", transport=httpx.MockTransport(handler)
        )
        downloader.download(self._advbench_spec())

    def test_http_failure_raises_actionable_error(self, tmp_path):
        def handler(_request):
            return httpx.Response(404, text="no")

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        with pytest.raises(DatasetError, match="Artifact not found"):
            downloader.download(self._advbench_spec())

    def test_max_samples_respected(self, tmp_path):
        def handler(_request):
            return httpx.Response(200, text="goal,target\na,1\nb,2\nc,3\n")

        downloader = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler))
        paths = downloader.download(self._advbench_spec(max_samples=2))
        assert len(_read_lines(paths["default"])) == 2


class TestAdvBenchData:
    """Schema-compatibility tests with a small fixture matching the verified
    ``goal,target`` schema of the official harmful_behaviors artifact."""

    CSV_FIXTURE = "goal,target\nbehavior 1,Sure, here is 1\nbehavior 2,Sure, here is 2\n"

    def _download(self, tmp_path, transport_handler):
        spec = DatasetSpec(
            dataset_id="advbench",
            name="AdvBench (official GitHub)",
            source="llm-attacks/llm-attacks",
            format="csv",
            splits=("default",),
            text_fields=("goal",),
            label_field=None,
            default_label=1,
            license="MIT",
            homepage="https://github.com/llm-attacks/llm-attacks",
            requires_token=False,
            source_type=DatasetSourceType.GITHUB,
            artifact_path="a62d1307e38b3a076e614b20781c785fd860d813/data/advbench/harmful_behaviors.csv",
        )
        return DatasetDownloader(
            tmp_path, transport=httpx.MockTransport(transport_handler)
        ).download(spec)

    def test_parses_columns_and_normalizes(self, tmp_path):
        def handler(_request):
            return httpx.Response(200, text=self.CSV_FIXTURE)

        paths = self._download(tmp_path, handler)
        records, filtered = DatasetRecordPreprocessor().preprocess(
            DatasetSpec(
                dataset_id="advbench",
                name="x",
                source="llm-attacks/llm-attacks",
                format="csv",
                text_fields=("goal",),
                label_field=None,
                default_label=1,
            ),
            paths,
        )
        assert filtered == 0
        assert len(records) == 2
        assert records[0].text == "behavior 1"
        assert records[0].label == 1
        assert records[0].category == GENERIC_MALICIOUS_CATEGORY

    def test_max_samples_caps_rows(self, tmp_path):
        def handler(_request):
            return httpx.Response(200, text=self.CSV_FIXTURE)

        spec = DatasetSpec(
            dataset_id="advbench",
            name="x",
            source="llm-attacks/llm-attacks",
            format="csv",
            splits=("default",),
            text_fields=("goal",),
            label_field=None,
            default_label=1,
            max_samples=1,
            source_type=DatasetSourceType.GITHUB,
            artifact_path="a62d1307e38b3a076e614b20781c785fd860d813/data/advbench/harmful_behaviors.csv",
        )
        paths = DatasetDownloader(tmp_path, transport=httpx.MockTransport(handler)).download(spec)
        records, filtered = DatasetRecordPreprocessor().preprocess(spec, paths)
        assert len(_read_lines(paths["default"])) == 1
        assert len(records) == 1
        assert filtered == 0
