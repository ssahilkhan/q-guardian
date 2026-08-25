"""Output monitoring package (P3-3).

Direction-gated analysis of agent output text: leakage, disclosure,
sensitive-data/credential exposure, actionable commands, obfuscated
payloads, and untrusted-content propagation. Reuses the existing
security pipeline (normalization, P1-1/P1-2 detectors, P3-5 context
preparation) and the shared decision engine.
"""

from __future__ import annotations

from q_guardian.output.monitor import (
    build_output_context,
    normalize_output,
    prepare_decoded_variants,
    resolve_output_config,
)
from q_guardian.output.rules import evaluate_output_rule

__all__ = [
    "build_output_context",
    "evaluate_output_rule",
    "normalize_output",
    "prepare_decoded_variants",
    "resolve_output_config",
]
