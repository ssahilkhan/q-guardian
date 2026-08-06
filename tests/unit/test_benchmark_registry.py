"""Unit tests for the dataset registry."""

from __future__ import annotations

import pytest

from q_guardian.benchmark.registry import DatasetRegistry, DatasetSpec


class TestDatasetRegistry:
    def test_builtin_has_public_datasets(self):
        registry = DatasetRegistry.builtin()
        ids = [s.dataset_id for s in registry.public()]
        assert "deepset-prompt-injections" in ids
        assert "jbb-behaviors" in ids
        assert "dolly-benign" in ids

    def test_gated_datasets_are_listed(self):
        registry = DatasetRegistry.builtin()
        assert len(registry.gated()) > 0
        for spec in registry.gated():
            assert spec.requires_token
            assert spec.format == "hf"

    def test_get_unknown_raises_key_error(self):
        registry = DatasetRegistry.builtin()
        with pytest.raises(KeyError):
            registry.get("does-not-exist")

    def test_custom_registry(self):
        spec = DatasetSpec(dataset_id="x", name="X", source="x")
        registry = DatasetRegistry([spec])
        assert registry.get("x").name == "X"

    def test_all_sorted(self):
        registry = DatasetRegistry.builtin()
        ids = [s.dataset_id for s in registry.all()]
        assert ids == sorted(ids)

    def test_spec_serializes(self):
        spec = DatasetRegistry.builtin().get("deepset-prompt-injections")
        data = spec.to_dict()
        assert data["dataset_id"] == "deepset-prompt-injections"
        assert data["license"] == "Apache-2.0"
        assert data["splits"] == ("train", "test")
