"""Security metrics computation and quality gates.

Runs the full corpus through the real pipeline and computes:
TP / TN / FP / FN, precision, recall, F1, accuracy, confusion matrix,
per-category detection rates, and benign acceptance rate.

Quality gates (calibrated for the rules-only production pipeline):
- 100% detection on required attack samples
- benign acceptance >= 80%
- precision >= 0.85 and recall >= 0.75 on the full corpus

The JSON artifact is written by ``scripts/qa/security_report.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.security.corpus import (
    ALL_SAMPLES,
    BENIGN_SAMPLES,
    INJECTION_SAMPLES,
    JAILBREAK_SAMPLES,
    OBFUSCATION_SAMPLES,
    CorpusCategory,
    RecordStatus,
    SecuritySample,
)

if TYPE_CHECKING:
    from tests.security.conftest import SecurityPipeline

ALLOWED = "allow"


def _is_flagged(pipeline: SecurityPipeline, sample: SecuritySample) -> bool:
    return pipeline.scan(sample.text).decision.value != ALLOWED


def _confusion(pipeline: SecurityPipeline) -> dict[str, int]:
    tp = tn = fp = fn = 0
    for sample in ALL_SAMPLES:
        flagged = _is_flagged(pipeline, sample)
        if sample.expect_flagged and flagged:
            tp += 1
        elif sample.expect_flagged and not flagged:
            fn += 1
        elif not sample.expect_flagged and flagged:
            fp += 1
        else:
            tn += 1
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


class TestSecurityMetrics:
    """Quantified security posture of the production rule pipeline."""

    def test_confusion_matrix_and_gates(self, pipeline: SecurityPipeline) -> None:
        cm = _confusion(pipeline)
        total = sum(cm.values())

        precision = _safe_div(cm["tp"], cm["tp"] + cm["fp"])
        recall = _safe_div(cm["tp"], cm["tp"] + cm["fn"])
        f1 = _safe_div(2 * precision * recall, precision + recall)
        accuracy = _safe_div(cm["tp"] + cm["tn"], total)

        # Documented gates for the rules-only pipeline.
        assert cm["fn"] == 0 or all(
            s.status == RecordStatus.KNOWN_GAP
            for s in ALL_SAMPLES
            if s.expect_flagged and not _is_flagged(pipeline, s)
        ), "Unexpected false negatives outside documented known gaps"
        assert precision >= 0.85, f"precision {precision:.3f} < 0.85"
        assert recall >= 0.75, f"recall {recall:.3f} < 0.75"
        assert f1 >= 0.80, f"F1 {f1:.3f} < 0.80"
        # Accuracy floor reflects the documented known-gap surface (lexical
        # evasion samples tracked as KNOWN_GAP in corpus.py).
        assert accuracy >= 0.80, f"accuracy {accuracy:.3f} < 0.80"

    def test_required_attack_detection_is_complete(self, pipeline: SecurityPipeline) -> None:
        required_attacks = [
            s for s in ALL_SAMPLES if s.status == RecordStatus.REQUIRED and s.expect_flagged
        ]

        missed = [s.text for s in required_attacks if not _is_flagged(pipeline, s)]

        assert not missed, f"Required attacks missed: {missed}"

    def test_benign_acceptance_rate(self, pipeline: SecurityPipeline) -> None:
        accepted = sum(1 for s in BENIGN_SAMPLES if not _is_flagged(pipeline, s))
        rate = accepted / len(BENIGN_SAMPLES)

        assert rate >= 0.80, f"benign acceptance {rate:.3f} < 0.80"

    def test_per_category_detection_rates(self, pipeline: SecurityPipeline) -> None:
        attack_categories = {
            CorpusCategory.INJECTION: INJECTION_SAMPLES,
            CorpusCategory.JAILBREAK: JAILBREAK_SAMPLES,
            CorpusCategory.OBFUSCATION: OBFUSCATION_SAMPLES,
        }

        for category, samples in attack_categories.items():
            required = [s for s in samples if s.status == RecordStatus.REQUIRED]
            detected = sum(1 for s in required if _is_flagged(pipeline, s))
            rate = detected / len(required)

            assert rate == 1.0, f"{category.value} required-sample detection {rate:.3f} != 1.0"

        # Overall obfuscation floor documents the known-gap surface.
        obf_detected = sum(1 for s in OBFUSCATION_SAMPLES if _is_flagged(pipeline, s))
        obf_rate = obf_detected / len(OBFUSCATION_SAMPLES)

        assert obf_rate >= 0.40, (
            f"obfuscation overall detection regressed below documented floor: {obf_rate:.3f}"
        )
