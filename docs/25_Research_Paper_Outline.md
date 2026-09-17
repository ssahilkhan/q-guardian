# 25. Research Paper — Outline & Abstract (DRAFT)

> **Status:** DRAFT OUTLINE — not yet a manuscript
> **Scope:** Faculty-facing paper for Q-Gaudrail (v1.1.0), grounded exclusively in
> committed artifacts: `reports/ml_baseline/baseline_metrics.json`,
> `reports/ml_external_study/final_report.json`, `leakage_report.json`,
> `docs/21_Training_Pipeline_Documentation.md`, `docs/22_Training_Pipeline_Audit_Report.md`
> (commit `e4b3718`), `docs/22_Backend_to_UI_Integration_Audit.md`, and
> `docs/quantum-analysis-research.md`.
> **Working title:** *Runtime Security of Autonomous AI Agents: Evaluation Rigor,
> Classical Fusion, and the (Absent) Quantum Advantage in Q-Guardian*.

---

## 1. Abstract (draft)

Autonomous and agentic large language models (LLMs) are vulnerable to prompt
injection and jailbreak attempts, yet most published defenses are evaluated
only against the data they were trained on, suppressing generalization
failure. This paper presents Q-Guardian, an open, hybrid quantum-classical
framework for the runtime security of AI agents, and reports the first
external-generalization evaluation of its 10-module detection stack
(rule engine + Isolation Forest, Random Forest, XGBoost, and a 5-qubit
Quantum Support Vector Machine fused by five strategies including Bayesian
log-odds fusion). On held-out internal splits the fused detector reaches a
ROC-AUC of 0.906 (validation) and 0.861 (test); on an externally sourced,
leakage-checked corpus (JailbreakBench Behaviors, 200 samples, 0% overlap
with training), the same model collapses to ROC-AUC 0.609 with a recall of
0.01 at the default threshold — validation-optimal thresholds do not
transfer. Applying an explicit false-positive-rate guardrail restores the
fused ROC-AUC 0.783 (F1 0.72) at a manageable 0.125 FPR, out-performing
standard calibration (Platt, isotonic) for this regime. Exactly this
protocol detects a second failure: a 5-qubit QSVM performs at chance
(ROC-AUC 0.500), matching its 5-dimensional classical baselines and
contributing nothing to fusion — we find no quantum advantage on this
task, and the framework therefore defaults quantum off. Under 9 classes of
adversarial perturbation (1,400 perturbed samples) every classical model
degrades by ~0.22 AUC. All artifacts, scripts, and splits are committed, and
the evaluation protocol itself (leakage detection, external validation,
threshold guardrails) is the paper's primary methodological contribution.

---

## 2. Proposed Title / Author / Venue Options

- Short title candidate: *Prompt-Security Generalization: External Validation
  and No Quantum Advantage in a Hybrid Detection Framework*
- Venue options: IEEE S&P Workshops (Security of AI), ACL (blackbox/security
  shared task), CCS Workshop on AI Security, or a CS3999 faculty report.

---

## 3. Section Outline

### 1. Introduction
- Motivation: agentic LLMs get unconstrained tool/environment access; prompt
  injection and jailbreaks are the primary runtime attack surface; defenses
  must be evaluated *off* their training distribution.
- Contribution list (4 items):
  1. Q-Guardian, a modular 10-module hybrid quantum-classical runtime
     security framework (v1.1.0, 2,753 tests passing, CI-clean).
  2. A generalization-focused evaluation protocol with automated leakage
     checks, an external leakage-free corpus, and an FPR guardrail.
  3. Empirical finding: internal evals overstate external performance;
     threshold guardrails beat calibration for transfer.
  4. Empirical finding: no quantum advantage for a 5-qubit QSVM on prompt
     classification; framework ships `quantum_enabled=false`.

### 2. Related Work
- Prompt-injection/jailbreak detection and its evaluation practices.
- Quantum ML claims (Havlíček et al. 2019 quantum kernels; Schuld et al.
  2020 VQC; Tang 2019 dequantization caveat) — framed via
  `docs/quantum-analysis-research.md` §2.
- Contrast: most prior evaluations train and test on the same corpus;
  JBB (JailbreakBench) provides a held-out external benchmark.
- Research gap: hybrid quantum-classical *externally evaluated* prompt
  security (no prior work found).

### 3. The Q-Guardian Framework
- Architecture: 10 modules (security pipeline, ML, quantum, fusion, risk,
  policy, response, observability, engine/API, integrations) — see
  `docs/00_Project_Overview.md`, `docs/06_Architecture_Documentation.md`.
- Detection path: normalize → validate → features (43 hand-crafted dims) →
  rule engine + classical detectors → fusion (confidence, adaptive,
  weighted-voting, stacking, Bayesian log-odds).
- Quantum layer: 5-qubit QSVM (ZZFeatureMap/angle encoding, 128 shots),
  backend abstraction, `LocalSimulatorBackend`; opt-in, research-only.
- Deployment surface: FastAPI console, auth (JWT + API keys, router-level),
  rate limiting, Docker/CI.
- Figures to include: end-to-end dataflow; module dependency graph
  (`docs/01_Project_Structure.md`).

### 4. Evaluation Protocol
- **Data**: 6-train-set composition (arm_d 6,269 + deepset 662 + TrustAIR
  jailbreaks 1,405 + TrustAIR regular 3,500 + JailbreakV 5,900 + Harmful
  Behaviors 520); leakage checks (JBB↔training 0.0%, Harmful Behaviors 2.12%
  documented); external corpus = JBB-Behaviors (200, 100/100 benign/malicious).
- **Protocol steps**: split hygiene → threshold sweep on internal validation
  only → transfer to external → FPR guardrail (limit 0.15) → adversarial
  robustness → QSVM/classical comparison at matched dimensionality.
- **Metrics**: ROC-AUC, PR-AUC, F1, precision/recall, FPR/FNR at stated
  thresholds, ECE/Brier for calibration, latency p50/p95, AUC degradation
  under perturbation.
- Reproducibility: seed 42, Python 3.12, sklearn 1.5, xgboost 2.0 (from
  `final_report.json.reproducibility`).

### 5. Results
- **Internal (held-out)**: fusion val AUC 0.906 / test AUC 0.861; per-provider
  test AUC XGB 0.923 > RF 0.881 > fusion 0.861 > IF 0.698 > rule 0.486;
  max-val-F1 operating point t=0.20 → F1 0.822, FPR 0.029.
- **External (JBB)**: at default t=0.5 the fusion emits 1 true positive
  (recall 0.01, F1 0.02, accuracy 0.50); at guardrail t=0.30 → ROC-AUC 0.783,
  F1 0.721, precision 0.656, recall 0.800, FPR 0.125; XGBoost strongest
  single provider (AUC 0.786 5). Table: per-provider × {internal test,
  external} AUC matrix.
- **Calibration transfer**: val-optimal t=0.15 → external FPR 0.700; Platt
  → 1.000; isotonic → 0.810; guardrail-selected t=0.30 → 0.125. Figure:
  FPR/label vs threshold on internal vs external.
- **Adversarial robustness**: 9 perturbation classes × 1,400 samples;
  AUC degradation fusion 0.218, XGB 0.233, RF 0.214, IF 0.218 — uniform
  ~0.22 across models.
- **Quantum vs classical**: QSVM external AUC 0.500 (F1 0.000) vs matched
  5-dim classical baselines RF 0.486 / XGB 0.488; full 427-dim XGB 0.786;
  fusion ablation (internal) removing QSVM → ROC-AUC 0.985 / F1 0.821
  (no degradation), removing XGB is the largest drop. Conclusion: no
  quantum advantage; O(n²) kernel caps training at 200 samples.
- **Latency**: p50 ≈ 24 ms, p95 ≈ 29–36 ms across pools.
- Artifacts pointer: every number traceable to the JSON/report files above.

### 6. Discussion & Limitations
- Why internal evals overstate external performance (distribution shift;
  threshold miscalibration vs score ranking).
- Guardrails > recalibration for production operating points.
- Quantum: 5-qubit/200-sample caps; no evidence of advantage; dequantization
  concern; what would be needed (>20 qubits / real QPU / higher-dim encoding).
- Limitations (from `final_report.json.limitations`): WildJailbreak not
  tested (needs HF_TOKEN) → generalization unidirectional; Harmful Behaviors
  ~2.12% overlap; binary label mapping forced by JBB split labels;
  rule/classical default (quantum off in scan path);
  42% FPR at t=0.50 on benign JBB; single external corpus.

### 7. Conclusion & Future Work
- Contributions restated; quantum remains research-only; production
  recommendation is classical-only fusion with FPR guardrail (choice A,
  `quantum_enabled=false`, weights rule 0.15 / IF 0.10 / RF 0.35 / XGB 0.25).
- Future work: WildJailbreak + multi-corpus external eval; embeddings
  (MiniLM/BGE/E5 hybrid, LRU cache) into the feature path; cloud-embedding
  vs handcrafted comparison; real-QPU QSVM with >20 qubits; adversarial
  training; publication + release to PyPI.

---

## 4. Key Figures & Tables Plan

| # | Kind | Content | Artifact source |
|---|------|---------|-----------------|
| F1 | Pipeline diagram | 10-module dataflow, quantum opt-in | `docs/06`, `docs/01` |
| F2 | Threshold transfer | Internal vs external FPR/label vs t | `baseline_metrics.json` sweeps vs `final_report` calibration |
| F3 | Fusion ablation | Frozen-fusion ROC/F1 per removed provider | `final_report.json` `ablation_impact` |
| T1 | Per-provider internal | AUC/F1/PR on val + test | `baseline_metrics.json` |
| T2 | Per-provider external | AUC/F1/precision/recall/FPR on JBB (t=0.30) | `final_report.json` |
| T3 | Quantum vs classical | 5-dim same-space + full-dim comparison | `final_report.json` `quantum_results` |
| T4 | Adversarial | AUC degradation per model | `final_report.json` `adversarial_robustness` |
| T5 | Calibration | raw/Platt/isotonic/guardrail → external FPR | `final_report.json` `calibration` |

---

## 5. Honest-Coverage Checklist (avoid overclaiming)

- [ ] Internal F1 (0.822–0.97) must NOT be quoted for external leadership.
- [ ] External F1 0.72 is at guardrail t=0.30; default t=0.5 collapses to 0.02.
- [ ] QSVM is evaluated at 5 dims / 200 samples — headline is *no advantage
      demonstrated in this regime*, not "quantum is useless".
- [ ] Detection-eval numbers in `docs/22_Training_Pipeline_Audit_Report.md`
      (F1 0.966 internal / 0.947 external) come from a separate controlled
      gold evaluation and should be reported in a separate subsection with
      its own protocol footnote.
- [ ] Harmful Behaviors overlap (2.12%) and binary-label mapping are stated.

---

## 6. Next Steps to Manuscript

1. Fill §4 methodology with exact pipeline command / script references
   (`scripts/train_data.py`, `scripts/evaluate_pipeline.py`,
   `scripts/ml/external_study_manifest.py`, benchmark runner).
2. Generate F2/F3 from the committed JSON sweeps (script exists for sweeps).
3. Add related-work citations (quantum ML + prompt-injection defense eval).
4. Decide venue + page budget; expand §4–§5 to full text; write §2.