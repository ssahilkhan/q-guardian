# Bayesian Fusion Strategy

`BayesianFusionStrategy` combines the continuous **threat probabilities**
reported by each detection provider into a single posterior belief about
whether a prompt is a threat. It is a registered, executable fusion
strategy (`name="bayesian"`) alongside Weighted Voting, Confidence Fusion,
Adaptive Fusion, and Stacking (the default).

> **Validation status — read this first.** This strategy is implemented and
> unit-tested for mathematical correctness and numerical robustness.
> Passing unit tests validate that the formulas are computed as documented,
> **not** that the resulting posterior is a scientifically validated
> probability estimate. Whether the fusion improves real threat detection
> (and whether any single provider dominates) must be established by
> benchmark/evaluation experiments, not by unit tests. No results are
> claimed here.

- [Bayesian Fusion Strategy](#bayesian-fusion-strategy)
  - [1. Architecture](#1-architecture)
  - [2. Mathematical Model](#2-mathematical-model)
  - [3. Prior Selection](#3-prior-selection)
  - [4. Evidence Interpretation](#4-evidence-interpretation)
  - [5. Conditional-Independence Assumptions](#5-conditional-independence-assumptions)
  - [6. Detector Reliability Handling](#6-detector-reliability-handling)
  - [7. Missing / Failed Detectors](#7-missing--failed-detectors)
  - [8. Configuration](#8-configuration)
  - [9. Explainability Output](#9-explainability-output)
  - [10. API / CLI Integration](#10-api--cli-integration)
  - [11. Limitations](#11-limitations)

---

## 1. Architecture

`BayesianFusionStrategy` extends the shared `FusionStrategy` ABC
(`src/q_guardian/quantum/fusion/strategies/base.py`). It consumes the same
`ThreatPrediction` lingua franca produced by every `PredictionProvider`
(rule, classical ML, quantum) and returns a standard `FusedPrediction`.

```
Provider Outputs (ThreatPrediction list)
        │
        ▼
validate_predictions()          # drop is_valid=False / failed detectors
        │
        ▼
Extract threat probability p_i  # probabilities["threat"] (per detector)
        │
        ▼
logit(p_i)  →  evidence log-odds
        │
        ▼
Weighted log-odds sum  (+ prior logit * prior_weight)
        │
        ▼
Posterior probability = sigmoid(·)
        │
        ▼
FusedPrediction (label, confidence, probabilities, risk_score, metadata)
```

There is **no special case for quantum providers**. Evidence from every
provider goes through the identical evidence model. A quantum provider
contributes weight only if it provides calibrated evidence; when it is
unavailable or missing it is simply absent from the sum (see §7).

---

## 2. Mathematical Model

Let `p` be the probability that the prompt is a threat and define the logit
(log-odds)

```
logit(p) = ln( p / (1 - p) )
```

**Prior.** A configured threat probability `p0` has prior log-odds
`L0 = logit(p0)`.

**Evidence.** Each available detector reports a threat probability `p_i`.
Its evidence, in log-odds space, is `L_i = logit(p_i)`. A neutral detector
(`p_i = 0.5`) has `L_i = 0` and therefore contributes no evidence — it is
indistinguishable from an absent detector.

**Posterior.** The posterior log-odds is the weighted sum

```
L_post = w0 * L0  +  Σ_i ( w_i * L_i )
```

and the posterior threat probability is

```
p_post = sigmoid(L_post) = 1 / (1 + exp(-L_post))
```

When every weight `w_i = w0 = 1` this is the standard naive-Bayes update

```
logit(p_post) = logit(p0) + Σ_i logit(p_i)
```

which is the **default** (`reliability_mode="uniform"`).

**Numerical stability.** All arithmetic is in log-odds space. Probabilities
are clamped to `[epsilon, 1 - epsilon]` (default `epsilon = 1e-12`) before
`logit`, and `sigmoid` is computed in its overflow-safe form for positive
arguments. This avoids `log(0)`, `log(1)`, NaN propagation, and infinite
posterior odds for extreme detector outputs. Every reported probability is
validated (`0 <= p <= 1`, finite) before use.

---

## 3. Prior Selection

The prior `p0` is **configurable** (default `0.5`, i.e. no prior belief).

- The default `0.5` is a **neutral** prior expressing complete ignorance of
  threat prevalence; with neutral evidence the posterior equals the prior.
- Because this repository does **not** fabricate or hard-code historical
  threat prevalence, no dataset-derived or historical prior is injected by
  default.
- To use a dataset-derived prevalence, set `prior` from your own validated
  measurement (e.g. observed threat rate on a held-out validation set). This
  is the operator's responsibility; the library documents but does not
  assume a source.

A `prior_weight` (`w0`, default `1.0`) scales how strongly the prior
influences the posterior.

---

## 4. Evidence Interpretation

Each detector's `p_i` is interpreted as its **reported probability of
threat** — i.e. `P(threat | detector_i)`. This is exactly the value the
provider adapters expose as `probabilities["threat"]` (and `risk_score`).

The strategy should be used with **calibrated** detectors. The
`ConfidenceCalibrator` (`method="none"` by default) does not statistically
calibrate raw scores; it only rescales/normalizes. Unless a detector's
outputs have been shown to be calibrated, treat `p_i` as a **relative
evidence signal**, not a rigorous calibrated probability. This is documented
as a limitation (§11).

The strategy does **not** fabricate evidence: a detector whose `threat`
probability is missing, `NaN`, infinite, or outside `[0,1]` is treated as
*missing* and contributes zero (see §7). It is never silently converted into
an arbitrary non-zero vote.

---

## 5. Conditional-Independence Assumptions

The naive unity-weight update (the default) assumes:

1. **Detectors are statistically independent conditional on the true
   class.** This is almost never exactly true in practice (diverse detectors
   are often positively correlated). The assumption is made explicit and is
   a documented limitation; it is not presented as a validated fact.
2. **Each `p_i` is a calibrated probability of threat.** If a detector is
   miscalibrated, the naive update's magnitude is distorted.

Because this repository does not yet provide per-detector correlation data,
**no attempt is made to correct for correlation**. The resulting posterior
is a *generative combination under stated assumptions*, not a scientifically
validated probability. Configuring `reliability_mode="configured"` with
empirically estimated weights is the operator's route to a more defensible
pool — but only if those weights come from a validated source.

---

## 6. Detector Reliability Handling

Reliability is handled through per-provider evidence weights `w_i`.

- **Default (`reliability_mode="uniform"`)** — every provider weight is `1.0`
  (naive Bayes). No unvalidated reliability assumptions are made, and no
  benchmark/train/test information leaks into runtime predictions.
- **`reliability_mode="configured"`** — operator-supplied `reliability` map,
  keyed by `provider_id`, scales each detector's log-odds evidence. A weight
  of `1.0` uses the raw evidence; `< 1.0` down-weights; `0.0` neutralises the
  detector entirely. Missing providers default to `1.0`.

The formula per detector is therefore `contribution_i = w_i * logit(p_i)`.

Reliability weights are **relative influence scalars**, not probabilities,
and they are **never derived automatically from benchmark metrics** in this
implementation. Benchmark precision/recall/accuracy is not automatically
plugged into the evidence model, because doing so without first
establishing that the metric is compatible with Bayesian log-odds evidence
would silently leak training/validation performance assumptions into runtime
predictions. Operators may set `reliability` explicitly from their own
validated measurements.

---

## 7. Missing / Failed Detectors

The implementation distinguishes these cases cleanly:

| Situation | Handling |
|-----------|----------|
| Detector available & valid | Evidence `logit(p_i)` added to posterior sum |
| Detector reports `p_i = 0.5` | Neutral — contributes `0` evidence (indistinguishable from absence) |
| Detector `is_valid=False` / raised | Dropped by `validate_predictions()`; counted in `num_failed`; contributes nothing |
| Detector reports invalid probability (`NaN`, `inf`, `<0`, `>1`) | Treated as **missing** — contributes `0`; never fabricated into evidence |
| Detector missing from the list | Simply absent from the sum |
| No valid detectors at all | Returns `unknown` / `confidence=0.0` empty result |

A failed or unavailable detector is **never** silently converted into
arbitrary or zero-as-benign evidence; it simply does not contribute. This
keeps a malfunctioning quantum provider from either inflating or deflating
the posterior.

---

## 8. Configuration

Bayesian fusion config lives on `QuantumFusionConfig.bayesian`
(`src/q_guardian/quantum/config.py`):

| Field | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `prior` | float | `0.5` | `[0,1]` | Prior threat probability |
| `decision_threshold` | float | `0.7` | `[0,1]` | Posterior above this → `threat` label |
| `epsilon` | float | `1e-12` | `(0,0.5)` | Logit stability floor |
| `reliability_mode` | str | `"uniform"` | `uniform`/`configured` | Weight strategy |
| `reliability` | dict | `{}` | weights `>= 0` | Per-provider evidence weights |
| `prior_weight` | float | `1.0` | `>= 0` | Prior log-odds weight |

Constructor parameters on `BayesianFusionStrategy(...)` mirror these and
validate them (raising `FusionError` on invalid values). Pydantic validates
config-layer values and rejects outright invalid input.

Per-call overrides are supported through `fuse(..., prior=..., decision_threshold=...)`
and are validated identically.

Example:

```python
from q_guardian.quantum.config import BayesianFusionConfig

cfg = BayesianFusionConfig(
    prior=0.3,
    decision_threshold=0.6,
    reliability_mode="configured",
    reliability={"classical-a": 1.0, "classical-b": 0.8},
)
```

---

## 9. Explainability Output

`fuse()` returns a `FusedPrediction` whose `metadata` exposes the Bayesian
explanation using **actual computed values** (never fabricated):

```text
Bayesian Fusion Result

Prior:                    0.5
Prior log-odds:           0.0
Available Evidence:       classical-a, classical-b
Evidence log-odds:        {classical-a: 1.609, classical-b: 0.405}
Posterior log-odds:       2.014
Posterior (threat):       0.882
Decision Threshold:       0.7
Final Decision:           THREAT
Reliability mode:         uniform
Assumption:               Conditional independence of detectors given the
                          true class; detector probabilities treated as
                          calibrated when no reliability data is configured.
```

The same values are reflected in `reasoning_summary` and in the standard
`FusedPrediction` fields (`probabilities["threat"]` = posterior,
`risk_score` = posterior, `predicted_label` = final decision).

`predict_with_uncertainty(...)` additionally returns `{fused_prediction,
posterior, evidence, credible_interval}`. Note the credible interval is
currently `None` and is **not** presented as a validated uncertainty bound.

---

## 10. API / CLI Integration

- **Engine**: use `engine.register_strategy(BayesianFusionStrategy())`
  followed by `engine.set_strategy("bayesian")`, or pass the strategy at
  construction. `engine.fuse(...)` delegates every provider through the same
  pipeline as any other strategy.
- **Registry**: `bayesian` is in `IMPLEMENTED_STRATEGIES`
  (`quantum/fusion/strategies/__init__.py`). The console API
  (`GET /api/v1/console/models`) advertises it as implemented via this
  registry; `INTERFACE_ONLY_STRATEGIES` no longer lists it.
- **Config**: selectable via `QuantumConfig.fusion.strategy =
  FusionStrategyType.BAYESIAN` with options under `fusion.bayesian`.

---

## 11. Limitations

1. **Conditional independence is assumed, not established.** Detectors are
   positively correlated in practice; the naive default overstates confidence
   for correlated ensembles.
2. **Calibration is not guaranteed.** Unless a detector is calibrated, the
   posterior is a relative evidence signal, not a rigorous probability.
3. **Reliability weights are not auto-derived.** No benchmark metric is
   silently converted into evidence weights, so configuration is the
   operator's responsibility and defaults make no reliability assumptions.
4. **No quantum advantage is implied or claimed.** Quantum evidence is
   treated identically to classical evidence; missing quantum providers are
   handled gracefully. Whether any provider — classical or quantum — helps
   must come from experiments.
5. **Unit tests validate math, not science.** Passing tests confirm formula
   correctness and numerical stability; they are not a benchmark or an
   external validation of detection efficacy.
6. **`update_posterior` is bookkeeping only** — it records observed outcomes
   for caller-side reliability studies but never mutates the runtime weights,
   to avoid silently interpolating unvalidated evidence into fusion.
7. **Credible intervals are not yet computed** (`predict_with_uncertainty`
   returns `None` bounds) and are not presented as validated uncertainties.
