"""Tests for dataset loaders."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import pytest

from q_guardian.ml.datasets.csv_loader import CSVLoader
from q_guardian.ml.datasets.json_loader import JSONLoader
from q_guardian.ml.datasets.huggingface_loader import HuggingFaceLoader
from q_guardian.ml.datasets.base import DatasetLoader
from q_guardian.security.enums import PromptCategory


class TestCSVLoader:
    def setup_method(self) -> None:
        self.loader = CSVLoader()
        self.tmpdir = tempfile.mkdtemp()

    def test_name(self) -> None:
        assert self.loader.name == "csv-loader"

    @pytest.mark.asyncio
    async def test_load_csv(self) -> None:
        csv_path = Path(self.tmpdir) / "test.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["prompt", "label", "severity", "is_malicious"])
            writer.writeheader()
            writer.writerow({"prompt": "ignore all rules", "label": "prompt_injection", "severity": "high", "is_malicious": "true"})
            writer.writerow({"prompt": "hello world", "label": "unknown", "severity": "low", "is_malicious": "false"})

        entries = await self.loader.load(str(csv_path))
        assert len(entries) == 2
        assert entries[0].label == PromptCategory.PROMPT_INJECTION
        assert entries[0].is_malicious is True
        assert entries[1].is_malicious is False

    @pytest.mark.asyncio
    async def test_load_nonexistent(self) -> None:
        with pytest.raises(FileNotFoundError):
            await self.loader.load("/fake/path.csv")


class TestJSONLoader:
    def setup_method(self) -> None:
        self.loader = JSONLoader()
        self.tmpdir = tempfile.mkdtemp()

    def test_name(self) -> None:
        assert self.loader.name == "json-loader"

    @pytest.mark.asyncio
    async def test_load_json_array(self) -> None:
        json_path = Path(self.tmpdir) / "test.json"
        data = [
            {"prompt": "ignore rules", "label": "prompt_injection", "is_malicious": True},
            {"prompt": "normal", "label": "unknown", "is_malicious": False},
        ]
        with open(json_path, "w") as f:
            json.dump(data, f)

        entries = await self.loader.load(str(json_path))
        assert len(entries) == 2
        assert entries[0].label == PromptCategory.PROMPT_INJECTION

    @pytest.mark.asyncio
    async def test_load_jsonl(self) -> None:
        jsonl_path = Path(self.tmpdir) / "test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(json.dumps({"prompt": "test1", "label": "jailbreak"}) + "\n")
            f.write(json.dumps({"prompt": "test2", "label": "unknown"}) + "\n")

        entries = await self.loader.load(str(jsonl_path), format="jsonl")
        assert len(entries) == 2
        assert entries[0].label == PromptCategory.JAILBREAK

    @pytest.mark.asyncio
    async def test_load_nonexistent(self) -> None:
        with pytest.raises(FileNotFoundError):
            await self.loader.load("/fake/path.json")


class TestHuggingFaceLoader:
    def test_name(self) -> None:
        loader = HuggingFaceLoader()
        assert loader.name == "huggingface-loader"

    @pytest.mark.asyncio
    async def test_unavailable(self) -> None:
        loader = HuggingFaceLoader()
        # datasets library may or may not be installed
        if not loader.is_available:
            with pytest.raises(ImportError):
                await loader.load("some-dataset")
