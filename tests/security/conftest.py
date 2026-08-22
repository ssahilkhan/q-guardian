"""Fixtures and helpers for the security test suite.

Provides the real production detection pipeline (normalizer -> validator ->
feature extractor -> rule engine -> decision engine) as a reusable fixture,
plus a ``scan`` helper returning the final PromptAnalysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from q_guardian.security.decision import SecurityDecisionEngine
from q_guardian.security.enums import ValidationStatus
from q_guardian.security.models import PromptAnalysis
from q_guardian.security.pipeline import (
    PromptFeatureExtractor,
    PromptNormalizer,
    PromptValidator,
    RuleEngine,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from q_guardian.security.models import PromptFeatures


@pytest.fixture(scope="session")
def normalizer() -> PromptNormalizer:
    """Session-scoped prompt normalizer."""
    return PromptNormalizer()


@pytest.fixture(scope="session")
def validator() -> PromptValidator:
    """Session-scoped prompt validator."""
    return PromptValidator()


@pytest.fixture(scope="session")
def feature_extractor() -> PromptFeatureExtractor:
    """Session-scoped feature extractor."""
    return PromptFeatureExtractor()


@pytest.fixture(scope="session")
def rule_engine() -> RuleEngine:
    """Session-scoped rule engine with default (production) rules."""
    return RuleEngine()


@pytest.fixture(scope="session")
def decision_engine() -> SecurityDecisionEngine:
    """Session-scoped decision engine with default thresholds."""
    return SecurityDecisionEngine()


class SecurityPipeline:
    """The real detection pipeline wired together for scanning."""

    def __init__(
        self,
        normalizer: PromptNormalizer,
        validator: PromptValidator,
        extractor: PromptFeatureExtractor,
        rule_engine: RuleEngine,
        decision_engine: SecurityDecisionEngine,
    ) -> None:
        self._normalizer = normalizer
        self._validator = validator
        self._extractor = extractor
        self._rule_engine = rule_engine
        self._decision_engine = decision_engine

    def scan(self, raw_prompt: str) -> PromptAnalysis:
        """Run the full pipeline on a raw prompt and return the analysis."""
        normalized = self._normalizer.normalize(raw_prompt)
        status, errors = self._validator.validate(normalized)

        features: PromptFeatures = self._extractor.extract(normalized)
        findings = self._rule_engine.analyze(normalized, features)

        analysis = PromptAnalysis(
            original_prompt=raw_prompt,
            normalized_prompt=normalized,
            is_valid=status == ValidationStatus.VALID,
            validation_status=status,
            validation_errors=errors,
            features=features,
            findings=findings,
        )
        return self._decision_engine.decide(analysis)


@pytest.fixture(scope="session")
def pipeline(
    normalizer: PromptNormalizer,
    validator: PromptValidator,
    feature_extractor: PromptFeatureExtractor,
    rule_engine: RuleEngine,
    decision_engine: SecurityDecisionEngine,
) -> Generator[SecurityPipeline, None, None]:
    """Session-scoped full detection pipeline."""
    yield SecurityPipeline(normalizer, validator, feature_extractor, rule_engine, decision_engine)
