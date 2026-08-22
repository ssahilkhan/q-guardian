"""Benign false-positive tests.

The security suite must not only catch attacks: it must also prove that
normal traffic passes. Required benign samples must be ALLOWED. Borderline
samples (security-education wording that trips lexical rules) are documented
false positives, asserted here to pin current behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.security.corpus import BENIGN_SAMPLES, RecordStatus

if TYPE_CHECKING:
    from tests.security.conftest import SecurityPipeline

REQUIRED_BENIGN = [s for s in BENIGN_SAMPLES if s.status == RecordStatus.REQUIRED]
BORDERLINE = [s for s in BENIGN_SAMPLES if s.status == RecordStatus.BORDERLINE]


@pytest.mark.parametrize("sample", REQUIRED_BENIGN, ids=[s.subcategory for s in REQUIRED_BENIGN])
class TestBenignAcceptance:
    """Required benign samples must be allowed without findings."""

    def test_benign_is_allowed(self, pipeline: SecurityPipeline, sample: object) -> None:
        analysis = pipeline.scan(sample.text)  # type: ignore[attr-defined]

        assert analysis.decision.value == "allow", (
            f"FALSE POSITIVE ({sample.subcategory}): {sample.text!r} "
            f"-> {analysis.decision.value} (findings: "
            f"{[f.rule_id for f in analysis.findings]})"
        )


@pytest.mark.parametrize("sample", BORDERLINE, ids=[s.subcategory for s in BORDERLINE])
class TestDocumentedFalsePositives:
    """Borderline samples are currently flagged; pin and document.

    If these start passing (allowed), promote them to REQUIRED â€” that is an
    improvement. If additional benign samples begin failing, investigate the
    rule change that caused new false positives.
    """

    def test_borderline_behavior_unchanged(
        self, pipeline: SecurityPipeline, sample: object
    ) -> None:
        analysis = pipeline.scan(sample.text)  # type: ignore[attr-defined]

        assert analysis.decision.value != "allow", (
            f"Behavior improved for borderline {sample.text!r}; promote it to REQUIRED in corpus.py"
        )
