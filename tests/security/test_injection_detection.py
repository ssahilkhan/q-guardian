"""Prompt injection detection tests.

Asserts that the production pipeline flags every ``required`` injection
sample in the corpus. A failure here is a security regression.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.security.corpus import INJECTION_SAMPLES, RecordStatus

if TYPE_CHECKING:
    from tests.security.conftest import SecurityPipeline

REQUIRED_INJECTIONS = [s for s in INJECTION_SAMPLES if s.status == RecordStatus.REQUIRED]


@pytest.mark.parametrize(
    "sample", REQUIRED_INJECTIONS, ids=[s.subcategory for s in REQUIRED_INJECTIONS]
)
class TestInjectionDetection:
    """Every required injection sample must be flagged (decision != ALLOW)."""

    def test_injection_is_flagged(self, pipeline: SecurityPipeline, sample: object) -> None:
        analysis = pipeline.scan(sample.text)  # type: ignore[attr-defined]

        assert analysis.decision.value != "allow", (
            f"MISSED injection ({sample.subcategory}): {sample.text!r} "
            f"was allowed with risk_score={analysis.risk_score}"
        )
        assert len(analysis.findings) > 0


def test_injection_subcategories_represented() -> None:
    """The corpus must cover all planned injection subcategories."""
    subcategories = {s.subcategory for s in INJECTION_SAMPLES}

    expected = {
        "instruction_override",
        "hierarchy_manipulation",
        "context_manipulation",
        "system_prompt_replacement",
        "policy_override",
        "boundary_attack",
        "system_prompt_extraction",
        "data_exfiltration",
    }
    assert expected <= subcategories
