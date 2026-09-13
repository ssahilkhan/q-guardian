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


class TestHexPhiSpec:
    def test_hex_phi_registered(self):
        registry = DatasetRegistry.builtin()
        spec = registry.get("hex-phi")
        assert spec.dataset_id == "hex-phi"

    def test_hex_phi_canonical_source(self):
        spec = DatasetRegistry.builtin().get("hex-phi")
        assert spec.source == "LLM-Tuning-Safety/HEx-PHI"

    def test_hex_phi_gated_classification_unchanged(self):
        spec = DatasetRegistry.builtin().get("hex-phi")
        assert spec.requires_token
        assert spec.format == "hf"
        assert spec.license == "research-only"

    def test_hex_phi_placeholder_schema_unchanged(self):
        spec = DatasetRegistry.builtin().get("hex-phi")
        assert spec.config is None
        assert spec.splits == ("default",)
        assert spec.text_fields == ("text",)
        assert spec.label_field is None

    def test_old_hex_phi_source_absent_from_registry(self):
        sources = [s.source for s in DatasetRegistry.builtin().all()]
        assert "walledai/HEx-PHI" not in sources

    def test_other_gated_sources_unaffected(self):
        sources = {s.dataset_id: s.source for s in DatasetRegistry.builtin().all()}
        assert sources["jailbreakbench-attacks"] == "JailbreakBench/JBB-Attacks"
        assert sources["harmbench-behaviors"] == "cais/harmbench_behaviors"
        assert sources["pal"] == "ProtectAI/PAL"
        assert sources["agentdojo"] == "ibm/agentdojo"
        assert sources["cyberseceval-prompt-injections"] == "facebook/CyberSecEval-PromptInjections"


class TestAdvBenchMigration:
    def test_advbench_is_not_gated_anymore(self):
        spec = DatasetRegistry.builtin().get("advbench")
        assert spec.requires_token is False
        assert spec.format == "csv"

    def test_advbench_uses_github_source_type(self):
        spec = DatasetRegistry.builtin().get("advbench")
        from q_guardian.benchmark.registry import DatasetSourceType

        assert spec.source_type is DatasetSourceType.GITHUB

    def test_advbench_authoritative_source(self):
        spec = DatasetRegistry.builtin().get("advbench")
        assert spec.source == "llm-attacks/llm-attacks"

    def test_advbench_artifact_path_pins_immutable_revision(self):
        spec = DatasetRegistry.builtin().get("advbench")
        first_segment = spec.artifact_path.split("/", 1)[0]
        assert len(first_segment) == 40
        assert all(c in "0123456789abcdef" for c in first_segment)
        assert spec.artifact_path.endswith("data/advbench/harmful_behaviors.csv")

    def test_advbench_old_hf_source_absent(self):
        sources = {s.dataset_id: s.source for s in DatasetRegistry.builtin().all()}
        assert "DeepMind/AdvBench" not in sources.values()

    def test_advbench_schema_maps_goal_with_default_malicious(self):
        spec = DatasetRegistry.builtin().get("advbench")
        assert spec.text_fields == ("goal",)
        assert spec.label_field is None
        assert spec.default_label == 1
