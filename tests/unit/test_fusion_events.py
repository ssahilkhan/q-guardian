"""Unit tests for Phase 3 fusion events."""

from __future__ import annotations

from q_guardian.quantum.events import (
    ConfidenceCalibrationApplied,
    FusionEngineInitialized,
    FusionStrategySwitched,
    ProviderFailed,
    ProviderRegistered,
)


class TestFusionEvents:
    def test_engine_initialized_type(self):
        e = FusionEngineInitialized()
        assert e.event_type == "quantum.fusion.engine_initialized"

    def test_strategy_switched_type(self):
        e = FusionStrategySwitched()
        assert e.event_type == "quantum.fusion.strategy_switched"

    def test_provider_registered_type(self):
        e = ProviderRegistered()
        assert e.event_type == "quantum.fusion.provider_registered"

    def test_provider_failed_type(self):
        e = ProviderFailed()
        assert e.event_type == "quantum.fusion.provider_failed"

    def test_calibration_applied_type(self):
        e = ConfidenceCalibrationApplied()
        assert e.event_type == "quantum.fusion.calibration_applied"

    def test_all_have_id(self):
        for cls in [
            FusionEngineInitialized,
            FusionStrategySwitched,
            ProviderRegistered,
            ProviderFailed,
            ConfidenceCalibrationApplied,
        ]:
            e = cls()
            assert e.id is not None
            assert len(e.id) > 0

    def test_all_have_timestamp(self):
        for cls in [
            FusionEngineInitialized,
            FusionStrategySwitched,
            ProviderRegistered,
            ProviderFailed,
            ConfidenceCalibrationApplied,
        ]:
            e = cls()
            assert e.timestamp is not None
