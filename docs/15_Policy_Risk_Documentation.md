# 15 - Policy & Risk Engines

> Module: `src\q_guardian\policy\` ("Module 8" — Advanced Policy Engine) and
> `src\q_guardian\risk\` ("Module 7" — Risk & Decision Intelligence Engine).
> These two modules work together to turn raw detections into **enforced, explainable
> security decisions**.

---

## 1. Two Engines, One Pipeline

```
  ML / Quantum / Security plugins
                 │
                 ▼
     NormalizedPrediction ──────────────►  RISK ENGINE (Module 7)
                                          • ThreatScorer       (composite score)
                                          • TrustEngine        (provider reliability)
                                          • ConfidenceEngine   (calibrate/normalize)
                                          • SeverityEngine     (score → severity)
                                          • RiskAssessmentEngine (orchestrator)
                                          • PolicyEngine       (4 built-in policies)
                                          • ActionEngine       (execute decision)
                                          • ExplanationEngine  (reasoning graph)
                                          • AuditTrail         (immutable records)
                 │
                 ▼
        PolicyDecision / ActionResult / Explanation
                 │
                 ▼
   POLICY ENGINE (Module 8) — policy-as-code framework
      • condition parser (AND/OR/NOT, regex, temporal)
      • PolicyRegistry + versioning (semver snapshots)
      • ConflictDetector (redundant / shadowed / contradicting)
      • SimulationEngine (dry-run, overrides, replay, compare)
      • DSL adapters (Rego, Cedar, YAML, JSON)
      • RBAC (admin / editor / viewer)
      • PolicyComposer (templates, inheritance, merge)
```

The **risk engine** is lightweight and built for real-time decisions; the **policy
engine** is a full policy-as-code framework used for authored, versioned, simulated,
composable policies. The SDK routes `calculate_risk` and `enforce_policy` to plugins
implementing the `risk_engine` / `policy_engine` interfaces.

---

## 2. Risk Engine — `src\q_guardian\risk\`

### 2.1 Assessment pipeline (`RiskAssessmentEngine.assess`)

```
NormalizedPrediction
  1. TrustEngine.get_provider_reliability(provider_id)      → reliability
  2. ThreatScorer.score(prediction, reliability, severity)  → ThreatScore
  3. ConfidenceEngine.normalize(prediction.confidence)      → ConfidenceScore
  4. SeverityEngine.classify(threat_score)                  → SeverityScore
  5. risk_score = threat * 0.7 + confidence * 0.3           (clamped, 6 dp)
  6. risk_level  = _score_to_risk_level(risk_score)
  7. TrustEngine.get_trust(provider_id)                     → trust_scores
```

**Risk level mapping:** `>=0.9` CRITICAL · `>=0.7` SEVERE · `>=0.5` HIGH ·
`>=0.3` MODERATE · `>=0.1` LOW · else MINIMAL.

### 2.2 Threat scoring formula (`ThreatScorer`)

```
threat_score = w_prob·probability + w_conf·confidence + w_rel·reliability
             + w_agr·agreement    + w_div·diversity    + w_sev·severity
```

Default `ScoringWeights`: `probability=0.30`, `confidence=0.25`,
`reliability=0.15`, `agreement=0.15`, `diversity=0.10`, `severity=0.05`.
`_score_to_level`: `>=0.9` CRITICAL · `>=0.7` HIGH · `>=0.4` MEDIUM ·
`>=0.1` LOW · else NONE.

### 2.3 Confidence engine

| Method | Behavior |
|---|---|
| `NONE` | pass-through (clamp 0–1) |
| `TEMPERATURE` | logit transform, sigmoid with temperature `T` (`logit/T`) |
| `MIN_MAX` | min-max normalize (needs count ≥ 2; degenerate range → 0.5) |
| `Z_SCORE` | `z = (x − mean)/std` then sigmoid (needs count ≥ 2) |
| `AGGREGATE` | dispatch for `aggregate()` |

Aggregation: `weighted_average` (default) or `geometric_mean`. Confidence interval:
`< 2` samples → ±0.1 band; else `1.96·std/√n` (≈95% CI). Running stats use
**Welford's online algorithm**.

### 2.4 Trust engine (`TrustEngine`)

- Defaults: `initial_trust=0.5`, `decay_rate=0.01`, `adjustment_rate=0.1`,
  `history_window=100`, trust clamped to `[0.0, 1.0]`.
- Delta per reason (unless `magnitude` overrides): CORRECT → `+rate`;
  INCORRECT → `−rate`; FALSE_POSITIVE → `−rate·1.2`; FALSE_NEGATIVE → `−rate·1.5`;
  TIMEOUT → `−rate·0.5`; MANUAL_OVERRIDE → magnitude or `+rate`; DECAY → `−decay_rate`.
- `_score_to_level`: `>=0.9` VERIFIED · `>=0.7` HIGH · `>=0.4` MODERATE ·
  `>=0.2` LOW · else UNTRUSTED.

### 2.5 Built-in policies (`risk\policy\policies.py`)

| Policy | default_action | Rules (condition → action, severity, priority) |
|---|---|---|
| `default-security` | ALLOW | `risk_level=='critical'` → BLOCK/CRITICAL/0; `=='severe'` → ESCALATE/HIGH/10; `=='high'` → REVIEW/HIGH/20; `=='moderate'` → WARN/MEDIUM/30; `=='low'` → LOG/LOW/40 |
| `strict-security` | WARN | `in ['critical','severe']` → BLOCK/CRITICAL/0; `=='high'` → BLOCK/HIGH/10; `=='moderate'` → REVIEW/MEDIUM/20; `=='low'` → WARN/LOW/30 |
| `permissive-security` | ALLOW | `=='critical'` → BLOCK/CRITICAL/0; `in ['severe','high']` → LOG/MEDIUM/10 |
| `quarantine-security` | ALLOW | `in ['critical','severe']` → QUARANTINE/HIGH/0; `=='high'` → REVIEW/MEDIUM/10 |

Condition language: comparison ops (`>= <= > < == !=`), `key in [v1, v2]`, float-or-string
value parsing. Context keys: `risk_score`, `risk_level`, `severity`, `confidence`,
`threat_score`, `threat_level`. Lowest priority value wins (first match on ties).

### 2.6 Action execution (`ActionEngine`)

| PolicyAction | Default responder | Result `action_type` |
|---|---|---|
| ALLOW | `ContinueResponder` | `continue` |
| WARN | `AlertResponder` | `alert` |
| LOG / REVIEW | `AuditLogResponder` | `audit_log` |
| BLOCK / QUARANTINE / TERMINATE_SESSION | `BlockResponder` | `block` |
| ESCALATE | `NotifyAdminResponder` | `notify_admin` |
| CUSTOM | `WebhookResponder` | `webhook` (placeholder) |

`AlertResponder` picks `Severity.HIGH` if `risk_score >= 0.7` else `Severity.MEDIUM`.
Actions are recorded to the immutable `AuditTrail`; `Notifier` fans out to
`default` / `alert` / `escalation` channels (in-memory by default).

### 2.7 Explainability

`ExplanationEngine.explain(assessment, decision, action_result, format)` →
builds a **reasoning graph** then a report.

```
INPUT → PROCESS(Threat Scoring) → CONFIDENCE(Normalization) → RISK(Severity)
      → RISK(Risk Assessment) → TRUST (one node/provider) → POLICY(Policy: <name>)
      → ACTION(Action: <action>)
edges: "scored by" → "calibrated" → "classified" → "determines risk"
     → "provider trust" → "evaluated by" → "prescribes"
```

One-line summary: `Risk {score} ({level}) -> Policy '{name}' -> {action} ({outcome})`.
Formats: `STRUCTURED`, `JSON`, `TEXT`, `MARKDOWN`.

### 2.8 Risk events (framework `Event` subclasses)

`RiskCalculated` → `risk.score.calculated` · `ThreatScored` → `risk.threat.scored` ·
`TrustUpdated` → `risk.trust.updated` · `PolicyMatched` → `risk.policy.matched` ·
`PolicyExecuted` → `risk.policy.executed` · `ActionExecuted` → `risk.action.executed` ·
`ExplanationGenerated` → `risk.explanation.generated` ·
`RiskAssessmentCompleted` → `risk.assessment.completed`.

### 2.9 `RiskAnalysisPlugin` (integration point)

- `name="risk-analysis"`, `version="1.0.0"`, `interfaces=["risk_analyzer"]`.
- `assess(prediction)` runs the full pipeline and returns `assessment`, `decision`,
  `action`, `explanation` (model_dump) + `processing_time_ms`; publishes
  `RiskCalculated` / `RiskAssessmentCompleted`.
- Storage: `RiskStorage` JSON layout — `risk_storage/assessments`, `audit`,
  `explanations`.

---

## 3. Advanced Policy Engine — `src\q_guardian\policy\`

### 3.1 Condition language (`core\condition_parser.py`)

Recursive-descent parser (tokenizer → `OR → AND → NOT → PRIMARY`):

| Category | Operators / keywords |
|---|---|
| Comparison | `==`, `!=`, `>`, `>=`, `<`, `<=` |
| Regex | `=~` (MATCHES), `!~` (NOT_MATCHES) |
| Membership | `in [a, b]`, `not_in [a, b]` |
| String | `contains`, `starts_with`, `ends_with` |
| Temporal | `after 'date'`, `before 'date'` (→ GTE/LTE on ISO datetime, UTC) |
| Existence | `exists` (→ `EQ "__exists__"`, type `EXISTS`) |
| Logical | `AND`, `OR`, `NOT` + parentheses |

Example: `role == 'admin' OR (request.path contains '/v1/agents' AND tokens >= 10)`

`Condition.evaluate` returns `False` when `context[field]` is `None` and operator is not
EQ/NEQ. Numeric comparison coerces to float; regex uses `re.search`.

### 3.2 Lifecycle, versions, simulation

- **Registry**: in-memory dict keyed by `policy_id`, optional JSON persistence
  (`policy_store.json`, `model_dump(mode="json")`, indent 2).
- **Statuses**: `DRAFT → ACTIVE → SUSPENDED / RETIRED / DELETED`.
- **Versioning** (`VersionManager`): snapshots per update, semver bump
  (`major` → `X.0.0`, `minor` → `X.Y.0`, patch/other → `X.Y.Z+1`; non-3-part → `1.0.0`),
  rollback returns a deep copy with version bumped (patch), retention cap `max_versions=50`.
- **Simulation** (`SimulationEngine`): dry-run `simulate`, `simulate_batch`,
  `simulate_with_overrides` (disable rules, override action/severity),
  `replay` (re-run stored contexts), `compare_policies`.
- **Conflict detection** (`ConflictDetector`): pairwise over enabled rules —
  same action + identical field sets → **REDUNDANT**; different actions + subsumed field
  sets → **SHADOWED** (higher-priority wins); different actions + overlapping fields →
  **CONTRADICTING**. Auto-detected at registration; raises `PolicyConflictError` unless
  `allow_overlapping_rules=True`.

### 3.3 Evaluation (`core\evaluator.py`)

- Sorts enabled rules by `priority` **ascending** (= highest priority first).
- **Winning rule** = first match in priority order (`matched_rules = [winning_id]`);
  `all_matching_rules` collects every match.
- Timeout abort when `elapsed_ms > timeout_seconds * 1000` (default 5.0 s).
- No match → `default_action` / `default_action_params` / `default_severity`.

### 3.4 DSL adapters (`policy\adapters`)

| Adapter | Format | Import behavior |
|---|---|---|
| `RegoAdapter` | OPA Rego | regex-extracts `package`, `default`, rule blocks; AND-combines conditions; rules named `rego_<action>` |
| `CedarAdapter` | AWS Cedar | `permit`→`allow`, `deny`→`block`; `when` body conditions; rules named `cedar_<effect>`; policy `cedar-imported` |
| `YAMLAdapter` | YAML | minimal line-based parser (no pyyaml dep); rule dicts `field/operator/value/...` |
| `JSONAdapter` | JSON | `json.loads` → same rule dict structure |

`get_adapter(fmt)` raises `DSLAdapterError` for unregistered formats.
`engine.import_from_dsl(raw, fmt)` auto-registers the converted policy;
`engine.export_to_dsl(policy_id, fmt)` exports.

### 3.5 RBAC (`policy\rbac\RBACManager`)

Built-in roles:
- **admin** — all permissions.
- **editor** — POLICY_CREATE/READ/UPDATE/EVALUATE/ACTIVATE/DEACTIVATE/SIMULATE.
- **viewer** — POLICY_READ/EVALUATE/SIMULATE.

`require_permission` raises `RBACError` on failure; built-in roles cannot be deleted.

### 3.6 Composition (`policy\composition\PolicyComposer`)

- `inherit(parent, child_name, overrides, rule_overrides)` — deep-copies, sets
  `parent_policy_id`, enforces `max_inheritance_depth` (default 5).
- `merge(base, overlay, strategy)` — strategies `override` (same-name rules replaced),
  `append`, `interleave` (sort by priority); name = `"{base}+{overlay}"`.
- `apply_template(template, policy_name, context)` — substitutes `${key}` placeholders.
- `get_inheritance_chain(policy, all_policies)` — walks parent chain (cycle-safe).

### 3.7 Policy engine events

`PolicyRegistered`, `PolicyUpdated`, `PolicyEvaluated`, `PolicyConflictDetected`,
`PolicySimulated`, `PolicyActivated`, `PolicyDeactivated` (all extend `PolicyEvent`).

---

## 4. Reference Cheat-Sheet

### Risk quick start

```python
from q_guardian.risk import RiskAssessmentEngine, RiskConfig
from q_guardian.risk.data import NormalizedPrediction

engine = RiskAssessmentEngine(RiskConfig())
pred = NormalizedPrediction(predicted_label="malicious", confidence=0.85, risk_score=0.75)
assessment = engine.assess(pred)  # RiskAssessment
```

### Advanced policy quick start

```python
from q_guardian.policy.engine import AdvancedPolicyEngine
from q_guardian.policy import AdvancedPolicyDefinition, AdvancedRule, Condition

engine = AdvancedPolicyEngine()
pol = AdvancedPolicyDefinition(
    name="no-admin-shell",
    rules=[
        AdvancedRule(
            name="deny-admin",
            condition=Condition(field="role", operator="==", value="admin"),
            action="block",
            priority=10,
        )
    ],
)
engine.register_policy(pol)
engine.activate_policy(pol.policy_id)
result = engine.evaluate({"role": "admin"})  # PolicyEvaluationResult
```

### Key enums — risk

| Enum | Members |
|---|---|
| `ThreatLevel` | none, low, medium, high, critical |
| `RiskLevel` | minimal, low, moderate, high, severe, critical |
| `Severity` | low, medium, high, critical |
| `TrustLevel` | untrusted, low, moderate, high, verified |
| `PolicyAction` | allow, warn, log, review, block, quarantine, terminate_session, escalate, custom |
| `DecisionOutcome` | allowed, warned, logged, pending_review, blocked, quarantined, session_terminated, escalated, custom_action |
| `ConfidenceMethod` | none, temperature, min_max, z_score, aggregate |

### Key enums — policy

| Enum | Members |
|---|---|
| `ComparisonOperator` | `==`, `!=`, `>`, `>=`, `<`, `<=`, `=~`, `!~`, `in`, `not_in`, `contains`, `starts_with`, `ends_with` |
| `LogicalOperator` | and, or, not |
| `ConditionType` | comparison, compound, temporal, regex, exists |
| `ConflictType` | overlapping, shadowed, contradicting, redundant |
| `ConflictResolution` | priority, most_restrictive, most_permissive, first_match, manual |
| `DSLFormat` | rego, cedar, yaml, json, custom |
| `Permission` | policy_create/read/update/delete/evaluate/activate/deactivate/simulate/export/import/admin |

---

## 5. Dependency Notes

- Only `risk\` and `policy\` reference each other's internals; no other framework
  subsystem imports them directly.
- Shared infrastructure: `utils.uuid_utils.generate_uuid` (risk IDs),
  `events.base.Event` (risk events), `exceptions.base.ApplicationException` (risk errors),
  `framework.context.FrameworkContext` + `plugins.base.Plugin` (RiskAnalysisPlugin).
- The two `PolicyEvaluator`s are **independent**: `policy/core/evaluator.py` collects
  all matches + winning rule; `risk/policy/evaluator.py` selects the best-priority match.
- Exceptions: policy root `PolicyEngineError` (9 subclasses incl. `PolicyConflictError`,
  `ConditionParseError`, `DSLAdapterError`); risk root `RiskError` (subclass of
  `ApplicationException`, code `RISK_ERROR`; 7 subclasses incl. `PolicyNotFoundError`,
  `AssessmentError`, `ConfigurationError`).
