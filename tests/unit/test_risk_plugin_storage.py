"""Tests for RiskAnalysisPlugin and RiskStorage."""

import pytest
import tempfile
import os
from pathlib import Path
from q_guardian.risk.plugin import RiskAnalysisPlugin
from q_guardian.risk.storage import RiskStorage
from q_guardian.risk.config import RiskConfig
from q_guardian.risk.data import (
    NormalizedPrediction, RiskAssessment, AuditRecord, Explanation,
)
from q_guardian.risk.enums import RiskLevel, AuditStatus
from q_guardian.framework.context import FrameworkContext
from q_guardian.events.bus import EventBus


def _make_prediction(**kwargs) -> NormalizedPrediction:
    defaults = {"predicted_label": "threat", "confidence": 0.8, "risk_score": 0.7, "provider_id": "test"}
    defaults.update(kwargs)
    return NormalizedPrediction(**defaults)


class TestRiskAnalysisPlugin:
    def test_plugin_metadata(self):
        plugin = RiskAnalysisPlugin()
        assert plugin.name == "risk-analysis"
        assert plugin.version == "1.0.0"
        assert "risk_analyzer" in plugin.interfaces

    def test_plugin_health(self):
        plugin = RiskAnalysisPlugin()
        h = plugin.health()
        assert h["status"] == "healthy"
        assert h["assessment_count"] == 0

    def test_plugin_configuration(self):
        plugin = RiskAnalysisPlugin()
        c = plugin.configuration()
        assert c["enabled"] is True

    def test_plugin_custom_config(self):
        config = RiskConfig(enabled=False)
        plugin = RiskAnalysisPlugin(config)
        assert plugin.config.enabled is False

    def test_plugin_risk_engine(self):
        plugin = RiskAnalysisPlugin()
        assert plugin.risk_engine is not None

    def test_plugin_policy_engine(self):
        plugin = RiskAnalysisPlugin()
        assert plugin.policy_engine is not None

    def test_plugin_action_engine(self):
        plugin = RiskAnalysisPlugin()
        assert plugin.action_engine is not None

    def test_plugin_explanation_engine(self):
        plugin = RiskAnalysisPlugin()
        assert plugin.explanation_engine is not None

    @pytest.mark.asyncio
    async def test_assess(self):
        plugin = RiskAnalysisPlugin()
        bus = EventBus()
        ctx = FrameworkContext(
            logger=None,
            config=None,
            event_bus=bus,
            plugin_registry=None,
            hook_manager=None,
        )
        await plugin.initialize(ctx)
        await plugin.start()

        p = _make_prediction(risk_score=0.8, confidence=0.9)
        result = await plugin.assess(p)

        assert "assessment" in result
        assert "decision" in result
        assert "action" in result
        assert "explanation" in result
        assert "processing_time_ms" in result

    @pytest.mark.asyncio
    async def test_assess_batch(self):
        plugin = RiskAnalysisPlugin()
        bus = EventBus()
        ctx = FrameworkContext(
            logger=None, config=None, event_bus=bus,
            plugin_registry=None, hook_manager=None,
        )
        await plugin.initialize(ctx)
        await plugin.start()

        preds = [_make_prediction(risk_score=i * 0.2) for i in range(3)]
        results = await plugin.assess_batch(preds)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_assess_health_updates(self):
        plugin = RiskAnalysisPlugin()
        bus = EventBus()
        ctx = FrameworkContext(
            logger=None, config=None, event_bus=bus,
            plugin_registry=None, hook_manager=None,
        )
        await plugin.initialize(ctx)

        p = _make_prediction(risk_score=0.95)
        await plugin.assess(p)

        h = plugin.health()
        assert h["assessment_count"] == 1

    @pytest.mark.asyncio
    async def test_stop(self):
        plugin = RiskAnalysisPlugin()
        ctx = FrameworkContext(
            logger=None, config=None, event_bus=None,
            plugin_registry=None, hook_manager=None,
        )
        await plugin.initialize(ctx)
        await plugin.start()
        await plugin.stop()


class TestRiskStorage:
    def test_init_creates_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RiskStorage(tmpdir)
            assert (storage.root / "assessments").exists()
            assert (storage.root / "audit").exists()
            assert (storage.root / "explanations").exists()

    def test_save_and_load_assessment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RiskStorage(tmpdir)
            a = RiskAssessment(risk_score=0.8, risk_level=RiskLevel.HIGH)
            storage.save_assessment(a)
            loaded = storage.load_assessment(a.assessment_id)
            assert loaded["risk_score"] == 0.8

    def test_load_assessment_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RiskStorage(tmpdir)
            with pytest.raises(Exception):
                storage.load_assessment("nonexistent")

    def test_save_audit_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RiskStorage(tmpdir)
            r = AuditRecord()
            path = storage.save_audit_record(r)
            assert path.exists()

    def test_save_explanation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RiskStorage(tmpdir)
            e = Explanation(summary="test")
            path = storage.save_explanation(e)
            assert path.exists()

    def test_list_assessments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RiskStorage(tmpdir)
            a = RiskAssessment()
            storage.save_assessment(a)
            ids = storage.list_assessments()
            assert len(ids) == 1

    def test_list_audit_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RiskStorage(tmpdir)
            r = AuditRecord()
            storage.save_audit_record(r)
            ids = storage.list_audit_records()
            assert len(ids) == 1

    def test_delete_assessment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RiskStorage(tmpdir)
            a = RiskAssessment()
            storage.save_assessment(a)
            deleted = storage.delete_assessment(a.assessment_id)
            assert deleted is True
            assert len(storage.list_assessments()) == 0

    def test_delete_assessment_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RiskStorage(tmpdir)
            assert storage.delete_assessment("nope") is False

    def test_get_storage_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RiskStorage(tmpdir)
            a = RiskAssessment()
            storage.save_assessment(a)
            stats = storage.get_storage_stats()
            assert stats["assessment_count"] == 1
            assert stats["total_size_bytes"] > 0

    def test_default_storage_root(self):
        storage = RiskStorage()
        assert storage.root.exists()
        # cleanup
        import shutil
        if storage.root.name == "risk_storage":
            shutil.rmtree(storage.root, ignore_errors=True)
