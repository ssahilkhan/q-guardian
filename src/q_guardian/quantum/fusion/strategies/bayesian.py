"""BayesianFusionStrategy — probabilistic fusion of detector predictions.

This strategy combines the continuous ``threat`` probabilities reported by
each detector using a weighted logarithmic opinion pool expressed in
log-odds space. Under the naive-Bayes conditional-independence assumption
(see module docstring below) this is equivalent to a sequential Bayesian
update: the prior belief about a prompt being a threat is updated by each
detector's evidence, yielding a posterior threat probability.

Numerical stability is handled entirely in log-odds space, which avoids
intermediate probabilities of 0 or 1 (whose logs would be undefined) and
prevents underflow/overflow during many-detecttor fusion.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from q_guardian.quantum.exceptions import FusionError
from q_guardian.quantum.fusion.strategies.base import FusedPrediction, FusionStrategy

if TYPE_CHECKING:
    from q_guardian.quantum.fusion.prediction import ThreatPrediction

# A threat probability that is indistinguishable from "no evidence".
# Used to guard against log(0) / log of invalid values.
_EPSILON = 1e-12


class BayesianFusionStrategy(FusionStrategy):
    """Bayesian fusion via a weighted log-odds (logistic opinion) pool.

    Mathematical model
    ------------------
    Let ``p`` be the probability that a prompt is a threat. Define the
    logit (log-odds) function ``logit(p) = ln(p / (1 - p))``.

    The prior is a configured probability ``p0`` whose logit is
    ``L0 = logit(p0)``. Each available detector reports a threat
    probability ``p_i``; its evidence, expressed as a log-odds
    contribution, is ``L_i = logit(p_i)``. A neutral detector
    (``p_i = 0.5``) contributes ``L_i = 0`` and therefore adds no
    evidence — it is indistinguishable from an absent detector.

    The posterior log-odds is the weighted sum:

        L_post = w0 * L0  +  sum_i ( w_i * L_i )

    and the posterior threat probability is ``p_post = sigmoid(L_post)``.

    When every reliability weight ``w_i = w0 = 1`` this reduces to the
    standard naive-Bayes update

        logit(p_post) = logit(p0) + sum_i logit(p_i),

    which assumes the detectors are statistically independent conditional
    on the true class and that each reported ``p_i`` is a *calibrated*
    probability of threat. This naive (unity-weight) mode is the default
    because no per-detector reliability / correlation data is available in
    this repository. See the module docstrings and ``configuration`` for
    the documented limitations.

    Reliability weighting
    ---------------------
    When ``reliability_mode="configured"``, each detector's evidence is
    scaled by a non-negative weight ``w_i`` provided in ``reliability``
    (keyed by provider_id). A weight of 1.0 means "use the raw calibrated
    evidence", a weight below 1.0 down-weights a detector, and a weight of
    0.0 neutralises it entirely (contributing exactly zero evidence). A
    missing provider simply has no entry and is treated as having weight
    1.0. These weights are treated as *relative influence* scalars whose
    values must come from a validated source (e.g. calibration/validation
    studies) — they are not probabilities and never leak ground truth
    into runtime predictions.
    """

    def __init__(
        self,
        prior: float = 0.5,
        decision_threshold: float = 0.7,
        epsilon: float = _EPSILON,
        reliability_mode: str = "uniform",
        reliability: dict[str, float] | None = None,
        prior_weight: float = 1.0,
    ) -> None:
        """Configure the Bayesian fusion strategy.

        Args:
            prior: Prior probability that a prompt is a threat (0..1). A
                neutral default of 0.5 expresses "no prior belief". Must be
                a valid probability.
            decision_threshold: Threshold above which the posterior threat
                probability yields a ``threat`` label (0..1). Default 0.7 is
                a conservative decision boundary.
            epsilon: Small numerical-stability floor used to clamp
                probabilities before taking logits (must be > 0 and < 0.5).
            reliability_mode: ``"uniform"`` (unity weights — naive Bayes) or
                ``"configured"`` (use per-provider ``reliability`` weights).
            reliability: provider_id -> non-negative weight used in
                ``"configured"`` mode.
            prior_weight: Weight ``w0`` applied to the prior log-odds.
        """
        if not math.isfinite(prior) or not (0.0 <= prior <= 1.0):
            raise FusionError(f"Invalid prior probability: {prior!r}")
        if not math.isfinite(decision_threshold) or not (0.0 <= decision_threshold <= 1.0):
            raise FusionError(f"Invalid decision_threshold: {decision_threshold!r}")
        if not math.isfinite(epsilon) or not (0.0 < epsilon < 0.5):
            raise FusionError(f"Invalid epsilon: {epsilon!r}")
        if reliability_mode not in ("uniform", "configured"):
            raise FusionError(
                f"Invalid reliability_mode: {reliability_mode!r}. "
                "Expected 'uniform' or 'configured'."
            )
        if not math.isfinite(prior_weight) or prior_weight < 0.0:
            raise FusionError(f"Invalid prior_weight: {prior_weight!r}")

        self._prior = float(prior)
        self._threshold = float(decision_threshold)
        self._epsilon = float(epsilon)
        self._reliability_mode = reliability_mode
        self._reliability = self._validate_reliability(reliability)
        self._prior_weight = float(prior_weight)
        self._posterior_history: dict[str, float] = {}

    # ── Config / metadata ─────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "bayesian"

    @property
    def display_name(self) -> str:
        return "Bayesian Fusion"

    @property
    def description(self) -> str:
        mode = (
            "naive (uniform weights)"
            if self._reliability_mode == "uniform"
            else "reliability-weighted"
        )
        return f"Bayesian log-odds fusion over detector evidence ({mode})"

    @property
    def prior(self) -> float:
        return self._prior

    @property
    def decision_threshold(self) -> float:
        return self._threshold

    @property
    def reliability_mode(self) -> str:
        return self._reliability_mode

    @property
    def reliability(self) -> dict[str, float]:
        return dict(self._reliability)

    def configuration(self) -> dict[str, Any]:
        """Return the strategy configuration / defaults for documentation."""
        return {
            "prior": self._prior,
            "decision_threshold": self._threshold,
            "epsilon": self._epsilon,
            "reliability_mode": self._reliability_mode,
            "reliability": dict(self._reliability),
            "prior_weight": self._prior_weight,
            "assumption": (
                "Conditional independence of detectors given the true class; "
                "detector probabilities treated as calibrated when no reliability "
                "data is configured."
            ),
        }

    # ── Fusion ────────────────────────────────────────────────────────────

    def fuse(
        self,
        predictions: list[ThreatPrediction],
        weights: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> FusedPrediction:
        """Fuse detector predictions into a single Bayesian posterior.

        Args:
            predictions: Valid predictions from registered providers.
            weights: Optional provider_id -> weight mapping. These weights are
                treated as additional reliability scalars multiplied into each
                detector's evidence (log-odds) when ``reliability_mode`` is
                ``"configured"``. In ``"uniform"`` mode they are ignored unless
                explicitly supplied.
            **kwargs: Strategy-specific parameters. Supported keys:
                ``prior``, ``decision_threshold`` — optional per-call overrides
                of the configured values.

        Returns:
            A FusedPrediction with the posterior threat probability as the
            risk score and posterior mass as the probability distribution.
        """
        valid = self.validate_predictions(predictions)
        all_predictions = list(predictions)
        num_failed = len(all_predictions) - len(valid)

        if not valid:
            return self._empty_result(all_predictions)

        prior = self._apply_prior_override(kwargs)
        threshold = self._apply_threshold_override(kwargs)
        explicit_weights = weights or {}

        prior_logit = self._logit(prior)

        posterior_logit = self._prior_weight * prior_logit
        evidence_contributions: dict[str, float] = {}
        provider_contributions: dict[str, float] = {}

        for pred in valid:
            p_i = self._extract_threat_probability(pred)
            if p_i is None:
                continue

            log_odds_i = self._logit(p_i)
            rel_w = self._reliability_weight(pred.provider_id)
            if self._reliability_mode == "configured":
                w = rel_w * explicit_weights.get(pred.provider_id, 1.0)
            else:
                w = explicit_weights.get(pred.provider_id, 1.0)

            contribution = w * log_odds_i
            posterior_logit += contribution
            evidence_contributions[pred.provider_id] = round(contribution, 6)
            provider_contributions[pred.provider_id] = round(w, 6)

        evidence_contributions = dict(
            sorted(evidence_contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)
        )
        provider_contributions = dict(
            sorted(provider_contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)
        )

        posterior_prob = self._sigmoid(posterior_logit)
        benign_prob = 1.0 - posterior_prob

        best_label = "threat" if posterior_prob >= threshold else "benign"
        confidence = posterior_prob if best_label == "threat" else benign_prob

        metadata = {
            "prior": round(prior, 6),
            "prior_logit": round(prior_logit, 6),
            "posterior_logit": round(posterior_logit, 6),
            "decision_threshold": round(threshold, 6),
            "num_evidence": len(evidence_contributions),
            "num_missing_evidence": num_failed,
            "reliability_mode": self._reliability_mode,
            "evidence_log_odds": evidence_contributions,
            "assumptions": self.configuration()["assumption"],
        }

        return FusedPrediction(
            predicted_label=best_label,
            confidence=round(confidence, 6),
            probabilities={
                "benign": round(benign_prob, 6),
                "threat": round(posterior_prob, 6),
            },
            risk_score=round(posterior_prob, 6),
            strategy_name="bayesian",
            provider_contributions=provider_contributions,
            source_predictions=valid,
            num_providers=len(valid),
            num_failed=num_failed,
            reasoning_summary=(
                f"Bayesian posterior threat = {posterior_prob:.3f} "
                f"(prior {prior:.2f}, {len(evidence_contributions)} detectors) -> "
                f"{best_label}"
            ),
            metadata=metadata,
        )

    # ── Uncertainty / posterior bookkeeping ───────────────────────────────

    def predict_with_uncertainty(
        self,
        predictions: list[ThreatPrediction],
        prior_weights: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Bayesian fusion returning uncertainty and evidence detail.

        Returns:
            Dict with ``fused_prediction`` (FusedPrediction), ``posterior``,
            ``credible_interval`` and ``evidence``.
        """
        fused = self.fuse(predictions, weights=prior_weights, **kwargs)
        posterior = fused.risk_score
        evidence = dict(fused.metadata.get("evidence_log_odds", {}))
        return {
            "fused_prediction": fused,
            "posterior": posterior,
            "evidence": evidence,
            "credible_interval": {"lower": None, "upper": None},
        }

    def update_posterior(
        self,
        provider_id: str,
        outcome: bool,
        learning_rate: float = 0.1,
    ) -> None:
        """Record an observed outcome for a provider (bookkeeping only).

        This method tracks observed outcomes so that caller-side code can
        later derive empirical reliability. It does **not** mutate the
        configured reliability weights, because doing so from a single
        observation would silently interpolate unvalidated evidence into
        the fusion model.

        Args:
            provider_id: Provider identifier.
            outcome: Whether the provider was correct (True) or not (False).
            learning_rate: Reserved for compatibility; accepted for the
                interface but not used to mutate runtime weights.

        Raises:
            FusionError: If ``outcome`` is not a bool.
        """
        if not isinstance(outcome, bool):
            raise FusionError(f"Invalid outcome: {outcome!r} — expected bool")
        self._posterior_history[provider_id] = float(outcome)

    def posterior_recorded_count(self, provider_id: str) -> int:
        """Number of recorded outcomes for a provider (0 if none)."""
        return int(provider_id in self._posterior_history)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _extract_threat_probability(self, pred: ThreatPrediction) -> float | None:
        """Extract a validated threat probability from a detector output.

        Prefers the explicit ``threat`` key in ``probabilities``; falls back
        to the predicted-label confidence. Values outside [0,1], NaN or inf
        are treated as missing evidence (None) and contribute nothing —
        never as fabricated evidence.
        """
        probs = pred.probabilities or {}
        if "threat" in probs:
            p = probs["threat"]
        else:
            if pred.predicted_label in ("threat", "benign"):
                p = pred.confidence if pred.predicted_label == "threat" else 1.0 - pred.confidence
            else:
                p = pred.confidence
        try:
            p_float = float(p)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(p_float) or not (0.0 <= p_float <= 1.0):
            return None
        return p_float

    def _reliability_weight(self, provider_id: str) -> float:
        if self._reliability_mode == "configured":
            return self._reliability.get(provider_id, 1.0)
        return 1.0

    def _apply_prior_override(self, kwargs: dict[str, Any]) -> float:
        prior = kwargs.get("prior", self._prior)
        if not math.isfinite(prior) or not (0.0 <= prior <= 1.0):
            raise FusionError(f"Invalid per-call prior: {prior!r}")
        return float(prior)

    def _apply_threshold_override(self, kwargs: dict[str, Any]) -> float:
        threshold = kwargs.get("decision_threshold", self._threshold)
        if not math.isfinite(threshold) or not (0.0 <= threshold <= 1.0):
            raise FusionError(f"Invalid per-call decision_threshold: {threshold!r}")
        return float(threshold)

    def _logit(self, p: float) -> float:
        """Compute log-odds of a probability with stable clamping."""
        p = min(max(p, self._epsilon), 1.0 - self._epsilon)
        return math.log(p / (1.0 - p))

    def _sigmoid(self, x: float) -> float:
        """Numerically stable sigmoid: 1 / (1 + exp(-x))."""
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        z = math.exp(x)
        return z / (1.0 + z)

    @staticmethod
    def _validate_reliability(
        reliability: dict[str, float] | None,
    ) -> dict[str, float]:
        result: dict[str, float] = {}
        for pid, w in (reliability or {}).items():
            if not math.isfinite(w) or w < 0.0:
                raise FusionError(f"Invalid reliability weight for '{pid}': {w!r}")
            result[pid] = float(w)
        return result

    def _empty_result(self, all_predictions: list[ThreatPrediction]) -> FusedPrediction:
        return FusedPrediction(
            predicted_label="unknown",
            confidence=0.0,
            probabilities={},
            risk_score=0.0,
            strategy_name="bayesian",
            source_predictions=all_predictions,
            num_providers=0,
            num_failed=len(all_predictions),
            reasoning_summary="No valid predictions to fuse",
            metadata={"prior": round(self._prior, 6), "reason": "empty"},
        )
