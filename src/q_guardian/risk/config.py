"""Configuration for the Risk & Decision Intelligence Engine."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.risk.enums import ConfidenceMethod, Severity


class ScoringWeights(BaseModel):
    """Configurable weights for threat scoring components."""

    model_config = ConfigDict(populate_by_name=True)

    probability: float = Field(default=0.30, ge=0.0, le=1.0, description="Weight for probability")
    confidence: float = Field(default=0.25, ge=0.0, le=1.0, description="Weight for confidence")
    reliability: float = Field(
        default=0.15, ge=0.0, le=1.0, description="Weight for provider reliability"
    )
    agreement: float = Field(default=0.15, ge=0.0, le=1.0, description="Weight for model agreement")
    diversity: float = Field(
        default=0.10, ge=0.0, le=1.0, description="Weight for provider diversity"
    )
    severity: float = Field(default=0.05, ge=0.0, le=1.0, description="Weight for severity")


class SeverityMapping(BaseModel):
    """Custom mapping from score ranges to severity levels."""

    model_config = ConfigDict(populate_by_name=True)

    critical_threshold: float = Field(
        default=0.9, ge=0.0, le=1.0, description="Score >= this -> CRITICAL"
    )
    high_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Score >= this -> HIGH")
    medium_threshold: float = Field(
        default=0.4, ge=0.0, le=1.0, description="Score >= this -> MEDIUM"
    )
    low_threshold: float = Field(default=0.1, ge=0.0, le=1.0, description="Score >= this -> LOW")


class TrustConfig(BaseModel):
    """Configuration for the TrustEngine."""

    model_config = ConfigDict(populate_by_name=True)

    initial_trust: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Initial trust for new providers"
    )
    decay_rate: float = Field(default=0.01, ge=0.0, le=1.0, description="Trust decay per time unit")
    adjustment_rate: float = Field(
        default=0.1, ge=0.0, le=1.0, description="Trust adjustment speed"
    )
    min_trust: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum trust floor")
    max_trust: float = Field(default=1.0, ge=0.0, le=1.0, description="Maximum trust ceiling")
    history_window: int = Field(
        default=100, ge=1, description="Number of recent predictions to consider"
    )


class ConfidenceConfig(BaseModel):
    """Configuration for the ConfidenceEngine."""

    model_config = ConfigDict(populate_by_name=True)

    method: ConfidenceMethod = Field(
        default=ConfidenceMethod.NONE, description="Calibration method"
    )
    temperature: float = Field(default=1.0, gt=0.0, description="Temperature for scaling")
    aggregation_method: str = Field(
        default="weighted_average", description="How to aggregate confidences"
    )


class RiskConfig(BaseModel):
    """Top-level configuration for the Risk module."""

    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = Field(default=True, description="Enable risk engine")
    scoring_weights: ScoringWeights = Field(
        default_factory=ScoringWeights, description="Scoring weights"
    )
    severity_mapping: SeverityMapping = Field(
        default_factory=SeverityMapping, description="Severity thresholds"
    )
    trust: TrustConfig = Field(default_factory=TrustConfig, description="Trust engine config")
    confidence: ConfidenceConfig = Field(
        default_factory=ConfidenceConfig, description="Confidence config"
    )
    default_severity: Severity = Field(
        default=Severity.LOW, description="Default severity for unmapped threats"
    )
    max_risk_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Maximum risk score cap")
    min_risk_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum risk score floor"
    )
    audit_enabled: bool = Field(default=True, description="Enable audit logging")
    explanation_enabled: bool = Field(default=True, description="Enable explanation generation")
