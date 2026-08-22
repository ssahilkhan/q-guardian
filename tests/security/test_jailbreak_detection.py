"""Jailbreak detection tests.

Asserts that the production pipeline flags every ``required`` jailbreak
sample. Known-gap samples (hypothetical/indirect framing) are excluded from
hard assertions and tracked in the metrics report as documented limitations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.security.corpus import JAILBREAK_SAMPLES, RecordStatus

if TYPE_CHECKING:
    from tests.security.conftest import SecurityPipeline

REQUIRED_JAILBREAKS = [s for s in JAILBREAK_SAMPLES if s.status == RecordStatus.REQUIRED]
KNOWN_GAPS = [s for s in JAILBREAK_SAMPLES if s.status == RecordStatus.KNOWN_GAP]


@pytest.mark.parametrize(
    "sample", REQUIRED_JAILBREAKS, ids=[s.subcategory for s in REQUIRED_JAILBREAKS]
)
class TestJailbreakDetection:
    """Every required jailbreak sample must be flagged."""

    def test_jailbreak_is_flagged(self, pipeline: SecurityPipeline, sample: object) -> None:
        analysis = pipeline.scan(sample.text)  # type: ignore[attr-defined]

        assert analysis.decision.value != "allow", (
            f"MISSED jailbreak ({sample.subcategory}): {sample.text!r}"
        )


def test_known_gaps_are_documented(pipeline: SecurityPipeline) -> None:
    """Known-gap samples must remain known gaps.

    If this test fails because detection IMPROVED, update the corpus:
    move the sample to REQUIRED and note the improvement in the changelog.
    If it fails because a previously-flagged sample is now allowed,
    that is a security regression.
    """
    for sample in KNOWN_GAPS:
        analysis = pipeline.scan(sample.text)

        assert analysis.decision.value == "allow", (
            f"Detection improved for {sample.subcategory!r}; promote it to REQUIRED in corpus.py"
        )
