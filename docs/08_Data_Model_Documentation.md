# 08 - Data Model Documentation

> Module: `src\q_guardian\` — Data contracts for Q-Gaudrail v0.10.0rc1
> Scope: every Pydantic `BaseModel`, `@dataclass`, and domain enum that flows between
> runtime, security, ML, quantum, policy, risk, response, and observability layers.
> All models use UTC timestamps and UUID string identifiers (see `src\q_guardian\utils\uuid_utils.py`).

---

## 1. The Data Flow at a Glance

The diagram below shows the primary payload that travels through the Q-Gaudrail
pipeline. Every arrow is a Pydantic model instance handed from one engine to the next.

```
                         runtime.models.AgentRequest
                                        |
                                        v
        security.PromptFeatures <-- security.models ---> PromptAnalysis (findings+decision)
                                        |                   ^
                                        v                   |
                          ml.FeatureVector / DatasetEntry    |
                                        |                   |
                                        v                   |
                     quantum.data (CircuitResult/Inference) |
                                        |                   |
                                        v                   |
                     fusion  --->  FusedPrediction           |
                                        |                   |
                                        v                   |
                     risk.NormalizedPrediction              |
                                        |                   |
                     +--------------------------------------+
                                        |
                                        v
              risk.RiskAssessment (ThreatScore, Severity, Confidence, Trust)
                                        |
                                        v
              risk.PolicyDecision / response.PolicyDecision
                                        |
                    +-------------------+-------------------+
                    v                   v                   v
        response.ResponseResult    policy.PolicyEvalResult   runtime.RiskContext
        (+ quarantine/rollback/            |                 SecurityContext.update_risk()
         recovery/notification)            v
                                  observability: Metric, Trace, Span,
                                  Alert, HealthReport, AnalyticsReport
```

Two facts shape the whole model design:

1. **UUID by default** — every `*_id` field defaults to `generate_uuid()` from
   `q_guardian\utils\uuid_utils.py`; identifiers are strings, never integers.
2. **populate_by_name=True everywhere** — the module-wide convention (Pydantic v2
   `ConfigDict(populate_by_name=True)`) lets models accept both field names and
   constructor keywords, smoothing cross-module hand-off.

---

## 2. Runtime Models — `src\q_guardian\runtime\models.py`

The runtime layer is the *vocabulary layer*. Per its module docstring, every future
module (Prompt Security, Runtime Monitoring, Threat Detection, Policy Engine,
Quantum Engine, Dashboard) MUST use these objects. They contain no detection logic,
no ML, and no quantum algorithms.

### 2.1 Enumerations — `src\q_guardian\runtime\enums.py`

All are `class X(str, Enum)`.

| Enum | Members (string values) |
|------|-------------------------|
| `AgentStatus` | `inactive`, `active`, `error`, `disabled` |
| `SessionStatus` | `open`, `closed`, `expired`, `error` |
| `RequestStatus` | `pending`, `processing`, `completed`, `failed` |
| `ResponseStatus` | `success`, `error`, `timeout`, `blocked` |
| `MemoryType` | `short_term`, `long_term`, `episodic`, `semantic`, `working`, `vector` |
| `MemoryOperation` | `read`, `write`, `delete`, `search`, `update` |
| `ToolType` | `function`, `api`, `database`, `file`, `shell`, `custom` |
| `ThreatSeverity` | `low`, `medium`, `high`, `critical` |
| `ThreatType` | `prompt_injection`, `jailbreak`, `data_exfiltration`, `unauthorized_tool_use`, `anomalous_behavior`, `policy_violation`, `unknown` |

### 2.2 Core Entities

| Model | Purpose | Key fields |
|-------|---------|------------|
| `Agent` | Primary entity: identity, capabilities, lifecycle | `id` (uuid), `name` (required), `framework="unknown"`, `version="1.0.0"`, `capabilities=[]`, `status=AgentStatus.INACTIVE`, `created_at`/`updated_at`. Methods: `activate()`, `deactivate()`, `heartbeat()`. |
| `AgentSession` | One execution session grouping requests/responses | `session_id`, `conversation_id=""`, `agent_id` (required), `user_id=""`, `status=SessionStatus.OPEN`, `request_count=0`, `response_count=0`. Methods: `open()`, `close()`, `reset()`, `duration()`, `increment_requests()`, `increment_responses()`. |
| `AgentRequest` | One incoming prompt with full context | `request_id`, `session_id=""`, `agent_id=""`, `prompt` (required), `source="unknown"`, `attachments=[]`, `metadata={}` |
| `AgentResponse` | One agent output with performance data | `response_id`, `request_id=""`, `session_id=""`, `output=""`, `execution_time=0.0`, `token_usage=TokenUsage()` |
| `TokenUsage` | Token counters | `prompt_tokens=0`, `completion_tokens=0`, `total_tokens=0` |
| `ToolInvocation` | One tool execution lifecycle | `invocation_id`, `tool_name` (required), `tool_type=ToolType.FUNCTION`, `arguments={}`, `result=None`, `started_at`, `completed_at=None`, `duration=0.0`, `success=True`, `error=None` |
| `MemoryAccess` | One memory read/write for audit | `access_id`, `memory_type` (required), `operation` (required), `key` (required), `value=None`, `agent_id=""`, `session_id=""` |

### 2.3 Security-Facing Runtime Models

| Model | Purpose | Key fields |
|-------|---------|------------|
| `SecurityContext` | Live, aggregated security state, updated continuously by plugins | `trust_score=1.0`, `risk_score=0.0`, `confidence=0.0` (all clamped 0–1), `active_policies=[]`, `alerts=[]`, `violations=[]`, `blocked=False`. Methods: `update_trust()`, `update_risk()`, `add_alert()`, `add_violation()`, `block()`, `unblock()`. |
| `ThreatContext` | A detected threat handed to incident response | `threat_id`, `threat_type=ThreatType.UNKNOWN`, `severity=ThreatSeverity.LOW`, `confidence=0.0`, `indicators=[]`, `evidence={}`, `source="unknown"` |
| `RiskContext` | Structured calculated risk for an operation | `score=0.0` (0–1), `factors=[]`, `explanation=""`, `recommendation=""`, `calculated_at` |

**Consumers**: `runtime/context.py` imports the full set; `runtime/managers.py`
tracks `AgentRequest`, `AgentResponse`, `AgentSession`, `MemoryAccess`,
`ToolInvocation`; all models are re-exported at the top level by
`q_guardian/__init__.py`.

---

## 3. Security Models — `src\q_guardian\security\models.py`

The data contract between pipeline stages of the Prompt Security Engine.
All four models use `ConfigDict(populate_by_name=True)`.

### 3.1 Enumerations — `src\q_guardian\security\enums.py`

| Enum | Members |
|------|---------|
| `PromptSeverity` | `info`, `low`, `medium`, `high`, `critical` |
| `PromptCategory` | `prompt_injection`, `jailbreak`, `role_manipulation`, `system_prompt_leak`, `data_exfiltration`, `excessive_encoding`, `suspicious_formatting`, `oversized_prompt`, `malformed_input`, `unknown` |
| `PromptDecision` | `allow`, `warn`, `review`, `block` |
| `ValidationStatus` | `valid`, `invalid`, `warning` |

### 3.2 Model Table

| Model | Purpose | Key fields |
|-------|---------|------------|
| `PromptFeatures` | Structured features extracted by `PromptFeatureExtractor` | `length=0`, `word_count=0`, `line_count=0`, `token_estimate=0` (~4 chars/token), `special_char_count=0`, `code_block_count=0`, `url_count=0`, `markdown_usage=False`, `repeated_patterns=[]`, `entropy=0.0` (0–5 Shannon estimate), `suspicious_keywords=[]`, `has_unicode_escaped=False`, `has_html_tags=False`, `uppercase_ratio=0.0`, `digit_ratio=0.0`, `metadata={}` |
| `PromptFinding` | A single rule match produced by `RuleEngine` | `finding_id` (uuid), `rule_id=""`, `rule_name=""`, `category=UNKNOWN`, `severity=LOW`, `description=""`, `matched_text=""`, `confidence=0.0` (0–1), `metadata={}`, `timestamp` |
| `PromptRule` | A detection rule definition consumed by `RuleEngine` | `rule_id` (uuid), `name` (required), `description=""`, `category=UNKNOWN`, `severity=MEDIUM`, `patterns=[]`, `keywords=[]`, `enabled=True`, `confidence=0.8` (0–1), `metadata={}` |
| `PromptAnalysis` | The primary output of the security engine; aggregates everything | `analysis_id`, `original_prompt` (required), `normalized_prompt=""`, `is_valid=True`, `validation_status=VALID`, `validation_errors=[]`, `features=PromptFeatures()`, `findings=[]`, `decision=ALLOW`, `risk_score=0.0` (0–1), `recommendation=""`, `processing_time_ms=0.0`, `metadata={}`, `timestamp`. Properties: `finding_count`, `high_severity_count` (HIGH+CRITICAL). Method: `to_security_dict()` → keys `risk_score`, `decision`, `finding_count`, `high_severity_count`, `blocked`, `recommendation`, `categories`. |

### 3.3 Configuration — `src\q_guardian\security\config.py`

`PromptSecurityConfig(BaseModel)` with `ConfigDict(extra="allow")`. Notable defaults:

- `enabled=True`; `max_prompt_length=100_000`, `min_prompt_length=1`, `max_lines=10_000`
- `enabled_rules=[]` (empty = all enabled), `disabled_rules=[]`, `custom_rules=[]`
- `block_on_critical=True`, `block_on_high_count=2`, `review_on_high_count=1`,
  `warn_on_medium_count=1`
- `log_findings=True`, `log_normalized_prompt=False`
- Future ML/Quantum placeholders (`ml_enabled=False`, `ml_threshold=0.5`,
  `quantum_enabled=False`, `quantum_backend=""`)

---

## 4. ML Models — `src\q_guardian\ml\data.py`

All models use `ConfigDict(populate_by_name=True)`.

| Model | Purpose | Key fields |
|-------|---------|------------|
| `ModelMetadata` | Registered ML model metadata | `model_id` (uuid), `name` (required), `model_type` (required), `backend` (required), `version="1.0.0"`, `status=UNLOADED`, `artifact_path=""`, `training_samples=0`, `feature_count=0`, `tags=[]` |
| `InferenceResult` | Output of a single model inference | `result_id`, `model_name` (required), `is_anomaly=False`, `anomaly_score=0.0` (−1..1), `predictions={}`, `predicted_class=""`, `confidence=0.0`, `risk_score=0.0`, `findings: list[PromptFinding]=[]`, `processing_time_ms=0.0`, `timestamp` |
| `TrainingResult` | Training run result | `run_id`, `model_name` (required), `status` (required), `metrics={}`, `feature_importance={}`, `training_samples=0`, `validation_samples=0`, `training_time_s=0.0`, `cv_scores=[]`, `cv_mean=0.0`, `cv_std=0.0`, `error_message=""`, `artifact_path=""` |
| `FeatureVector` | Numeric features for model input | `vector_id`, `prompt_id=""`, `features=[]`, `feature_names=[]`, `source_model=""` |
| `EvaluationMetrics` | Classification evaluation | `accuracy/precision/recall/f1_score/auc_roc=0.0`, `true_positives`/…/`false_negatives=0`, `confusion_matrix=[]`, `per_class_metrics={}` |
| `DatasetEntry` | One labeled training/eval example | `entry_id`, `prompt` (required), `label: PromptCategory` (required), `severity=LOW`, `is_malicious=False` |

`ModelMetadata`, `InferenceResult`, `TrainingResult`, `FeatureVector`,
`EvaluationMetrics`, `DatasetEntry` are re-exported from `ml/__init__.py` and the
top-level `q_guardian/__init__.py`.

---

## 5. Quantum Models — `src\q_guardian\quantum\data.py`

All models are `BaseModel` with `populate_by_name=True`; all timestamps UTC.

| Model | Purpose | Key fields |
|-------|---------|------------|
| `CircuitResult` | Result of one circuit execution | `result_id`, `circuit_id=""`, `counts={}`, `probabilities={}`, `expectation_values={}`, `raw_result=None`, `backend=""`, `shots=0`, `execution_time_ms=0.0` |
| `QuantumCircuitInfo` | Circuit metadata | `circuit_id`, `name=""`, `circuit_type` (required), `num_qubits` (required), `depth=0`, `gate_count=0`, `gate_counts={}`, `encoding_type=None` |
| `QuantumModelMetadata` | Registered quantum model metadata | `model_id`, `name` (required), `model_type` (required), `backend_type` (required), `version="1.0.0"`, `status="unloaded"`, `num_qubits=0`, `feature_count=0`, `encoding_type=None`, `training_samples=0`, `artifact_path=""` |
| `BackendInfo` | Quantum backend capability | `name` (required), `backend_type` (required), `status=INITIALIZING`, `num_qubits=0`, `max_shots=8192`, `min_qubits=1`, `supports_simulation=True`, `supports_hardware=False`, `error_rate=None`, `connectivity=None`, `capabilities=[]` |
| `QuantumTrainingResult` | Quantum training run | `run_id`, `model_name` (required), `status="completed"`, `accuracy=0.0`, `loss=0.0`, `convergence_iteration=0`, `training_samples=0`, `total_training_time_s` (alias `training_time_s`), `metrics={}`, `cv_scores=[]`, `cv_mean=0.0`, `cv_std=0.0` |
| `QuantumInferenceResult` | Quantum inference output | `result_id`, `model_name` (required), `predictions={}`, `predicted_class=""`, `confidence=0.0`, `risk_score=0.0`, `circuit_result: CircuitResult | None = None`, `processing_time_ms=0.0` |
| `QuantumEvaluationMetrics` | Quantum evaluation | `accuracy/precision/recall/f1_score/auc_roc/false_positive_rate/false_negative_rate=0.0`, `circuit_depth=0`, `circuit_width=0`, `total_shots=0`, `inference_time_ms=0.0`, `memory_usage_mb=0.0`, `backend_used=""` |
| `FusedResult` | Legacy hybrid fusion output | `result_id`, `predictions={}`, `predicted_class=""`, `confidence=0.0`, `risk_score=0.0`, `quantum_contribution=0.0`, `classical_contribution=0.0`, `rule_contribution=0.0`, `fusion_strategy=""`, `source_results=[]` |

> Note: the newer Phase-3 fusion path produces `FusedPrediction` in
> `src\q_guardian\quantum\fusion\strategies\base.py`; `FusedResult` in `quantum\data.py`
> is the legacy variant.

### 5.1 Quantum Enumerations — `src\q_guardian\quantum\enums.py`

| Enum | Members |
|------|---------|
| `QuantumBackendType` | `simulator`, `qiskit_aer`, `qiskit_runtime`, `ibm_quantum`, `pennylane`, `cudaq`, `local`, `custom` |
| `EncodingType` | `angle`, `amplitude`, `zz_feature_map`, `pauli`, `custom` |
| `CircuitType` | `feature_map`, `variational`, `kernel`, `measurement`, `hybrid` |
| `MeasurementBasis` | `pauli_z`, `pauli_x`, `pauli_y`, `computational` |
| `QuantumModelType` | (per `quantum\enums.py`) |
| `ExecutionStatus` / `BackendStatus` | status vocabulary for runs and backends |
| `FusionStrategyType` | fusion strategy selector |
| `OptimizerType` | training optimizer selector |

---

## 6. Policy Models — `src\q_guardian\policy\data.py`

The Advanced Policy Engine's models (module 8). Helpers: `_utcnow()` →
`datetime.now(timezone.utc)`; `_uuid()` → `str(uuid.uuid4())`.

| Model | Purpose | Key fields |
|-------|---------|------------|
| `Condition` | Single comparison `field operator value` | `condition_id` (uuid), `field: str`, `operator: ComparisonOperator`, `value: Any`, `negated=False`, `condition_type=COMPARISON`. Methods: `evaluate(context)`, `_compare(actual, op, expected)`, `_coerce_equal()` (float-first comparison). |
| `CompoundCondition` | AND / OR / NOT logic tree | `condition_id`, `operator: LogicalOperator`, `conditions=[]` (nested Condition|CompoundCondition). `evaluate()`: empty → True; NOT → negate first child; AND → `all()`; OR → `any()`. |
| `AdvancedRule` | One policy rule | `rule_id`, `name=""`, `condition` (required), `action="allow"`, `action_params={}`, `severity="medium"`, `priority=0`, `enabled=True`, `tags=[]`, `valid_from=None`, `valid_until=None`. Methods: `is_temporal()`, `is_valid_now()`, `evaluate(context)`. |
| `AdvancedPolicyDefinition` | Full policy with lifecycle | `policy_id`, `name` (required), `version="1.0.0"`, `status=DRAFT`, `rules=[]`, `default_action="allow"`, `default_severity="low"`, `parent_policy_id=None` (composition/inheritance), `created_at`/`updated_at`. Method: `enabled_rules()`. |
| `PolicyVersion` | Immutable snapshot | `version_id`, `policy_id`, `version`, `policy_snapshot` (deep copy), `changelog=""`, `created_by=""` |
| `ConflictResult` | Two-rule/policy conflict | `conflict_id`, `conflict_type`, `rule_id_a`, `rule_id_b`, `policy_id_a=""`, `policy_id_b=""`, `resolution=PRIORITY`, `resolved=False`, `winning_rule_id=""` |
| `SimulationResult` | Dry-run simulation output | `simulation_id`, `policy_id`, `policy_name`, `input_context`, `matched_rules=[]`, `action="allow"`, `severity="low"`, `reasoning=[]`, `would_execute=True`, `execution_time_ms=0.0` |
| `PolicyEvaluationResult` | Result of evaluating a policy | `evaluation_id`, `policy_id`, `policy_name`, `policy_version=""`, `matched_rules=[]` (winners), `all_matching_rules=[]`, `action="allow"`, `severity="low"`, `reasoning=[]`, `context={}`, `execution_time_ms=0.0`, `timestamp` |
| `RBACPermission` | Role-based access entry | `permission_id`, `role: str`, `permissions: list[Permission]=[]`, `policy_ids=[]` (empty = all policies) |
| `DSLAdapterResult` | DSL conversion result | `result_id`, `source_format`, `target_format=CUSTOM`, `raw_source=""`, `policy=None`, `success=True`, `errors=[]`, `warnings=[]` |

### 6.1 Policy Enumerations — `src\q_guardian\policy\enums.py`

| Enum | Members |
|------|---------|
| `ComparisonOperator` | `==`, `!=`, `>`, `>=`, `<`, `<=`, `=~` (regex), `!~`, `in`, `not_in`, `contains`, `starts_with`, `ends_with` |
| `LogicalOperator` | `and`, `or`, `not` |
| `ConditionType` | `comparison`, `compound`, `temporal`, `regex`, `exists` |
| `PolicyStatus` | `draft`, `active`, `suspended`, `retired`, `deleted` |
| `ConflictType` | `overlapping`, `shadowed`, `contradicting`, `redundant` |
| `ConflictResolution` | `priority`, `most_restrictive`, `most_permissive`, `first_match`, `manual` |
| `DSLFormat` | `rego`, `cedar`, `yaml`, `json`, `custom` |
| `Permission` | `policy_create`, `policy_read`, `policy_update`, `policy_delete`, `policy_evaluate`, `policy_activate`, `policy_deactivate`, `policy_simulate`, `policy_export`, `policy_import`, `policy_admin` |

### 6.2 Kernel / Training Dataclasses — `src\q_guardian\quantum\kernels\*`

The quantum kernel trainer uses three `@dataclass` types (in addition to the Pydantic
models above):

| Dataclass | Purpose |
|-----------|---------|
| `KernelHyperparams` | hyperparameter grid for kernel search |
| `KernelCandidate` | one candidate kernel (params + score) |
| `KernelSearchResult` | search outcome (best kernel, ranking, timing) |

---

## 7. Risk Models — `src\q_guardian\risk\data.py`

The Risk & Decision Intelligence Engine's domain models (module 7). Standalone —
does not import from quantum/ml/security. Consumes
`NormalizedPrediction`/`FusedPrediction`-style inputs and produces its own
`RiskAssessment`, `PolicyDecision`, and `Explanation`. All models use
`populate_by_name=True` and `generate_uuid` default IDs.

| Model | Purpose | Key fields |
|-------|---------|------------|
| `NormalizedPrediction` | Source-agnostic input from any detector | `prediction_id`, `source_id=""`, `source_type=""` (`rule`/`ml`/`quantum`/`fused`), `model_name=""`, `predicted_label` (required), `confidence=0.0`, `probabilities={}`, `risk_score=0.0`, `reasoning_steps=[]`, `evidence=[]`, `rules_triggered=[]`, `feature_importances={}`, `is_valid=True`, `error_message=""` |
| `ThreatScore` | `ThreatScorer` output | `score_id`, `threat_score=0.0`, components: `probability`, `confidence`, `reliability`, `agreement`, `diversity`, `severity` (all 0–1), `threat_level=NONE`, `reasoning=[]` |
| `TrustScore` | Provider trust ledger | `provider_id` (required), `trust_score=0.5`, `trust_level=MODERATE`, `total_predictions=0`, `correct/incorrect_predictions=0`, `false_positives=0`, `false_negatives=0`, `accuracy=0.0`, `adjustment_history=[]` |
| `SeverityScore` | Severity mapping | `severity=LOW`, `score=0.0`, `reasoning=""`, `mapping_used="default"` |
| `ConfidenceScore` | Calibrated confidence | `raw_confidence=0.0`, `normalized_confidence=0.0`, `method=NONE`, `confidence_interval=None`, `aggregation_count=1` |
| `RiskAssessment` | **Primary output** | `assessment_id`, `prediction_id=""`, `risk_score=0.0`, `risk_level=MINIMAL`, `threat_score`, `severity`, `confidence`, `trust_scores={}`, `reasoning=[]`, `contributing_sources=[]`, `timestamp` |
| `PolicyRule` | One risk-policy rule | `rule_id`, `condition` (required, e.g. `'risk_score >= 0.9'`), `action` (required), `severity=MEDIUM`, `enabled=True`, `priority=0` (lower = higher priority) |
| `PolicyDefinition` | Risk-policy bundle | `policy_id`, `name` (required), `version="1.0.0"`, `enabled=True`, `rules=[]`, `default_action=ALLOW`, `default_severity=LOW` |
| `PolicyDecision` | Decision outcome | `decision_id`, `assessment_id=""`, `policy_id=""`, `policy_name=""`, `outcome=ALLOWED`, `action=ALLOW`, `severity=LOW`, `risk_score=0.0`, `matched_rules=[]`, `reasoning=[]`, `timestamp` |
| `ActionResult` | One executed action | `action_id`, `decision_id=""`, `action_type` (required), `success=True`, `message=""`, `details={}`, `execution_time_ms=0.0` |
| `AuditRecord` | Immutable audit trail | `record_id`, `assessment_id=""`, `decision_id=""`, `prediction_id=""`, `risk_score=0.0`, `risk_level=MINIMAL`, `severity=LOW`, `outcome=ALLOWED`, `action=ALLOW`, `contributing_sources=[]`, `reasoning=[]`, `policy_name=""`, `status=ACTIVE`, `created_at` |
| `ReasoningNode` | Explainability graph node | `node_id`, `node_type` (required), `label` (required), `description=""`, `value=None`, `confidence=1.0` |
| `ReasoningEdge` | Explainability graph edge | `edge_id`, `source_node_id`, `target_node_id`, `label=""`, `weight=1.0` |
| `ReasoningGraph` | Full explanation graph | `graph_id`, `assessment_id=""`, `nodes=[]`, `edges=[]`, `summary=""` |
| `Explanation` | Generated explanation | `explanation_id`, `assessment_id=""`, `decision_id=""`, `summary` (required), `why=""`, `which_models=[]`, `confidence_summary=""`, `risk_summary=""`, `policy_used=""`, `action_taken=""`, `reasoning_graph=None`, `format=STRUCTURED`, `export_data={}` |
| `Notification` | Alert notification payload | `notification_id`, `title` (required), `message` (required), `severity=LOW`, `recipient="admin"`, `channel="default"`, `sent=False` |

### 7.1 Risk Enumerations — `src\q_guardian\risk\enums.py`

| Enum | Members |
|------|---------|
| `ThreatLevel` | `none`, `low`, `medium`, `high`, `critical` |
| `RiskLevel` | `minimal`, `low`, `moderate`, `high`, `severe`, `critical` |
| `Severity` | `low`, `medium`, `high`, `critical` |
| `TrustLevel` | `untrusted`, `low`, `moderate`, `high`, `verified` |
| `PolicyAction` | `allow`, `warn`, `log`, `review`, `block`, `quarantine`, `terminate_session`, `escalate`, `custom` |
| `PolicySeverity` | `info`, `low`, `medium`, `high`, `critical` |
| `DecisionOutcome` | `allowed`, `warned`, `logged`, `pending_review`, `blocked`, `quarantined`, `session_terminated`, `escalated`, `custom_action` |
| `ActionType` | `audit_log`, `alert`, `event`, `block`, `continue`, `notify_admin`, `webhook`, `custom` |
| `AuditStatus` | `created`, `active`, `resolved`, `dismissed`, `escalated` |
| `ConfidenceMethod` | `none`, `temperature`, `min_max`, `z_score`, `aggregate` |
| `TrustAdjustmentReason` | `correct_prediction`, `incorrect_prediction`, `false_positive`, `false_negative`, `timeout`, `manual_override`, `decay`, `bootstrap` |
| `ExplanationFormat` | `json`, `text`, `markdown`, `structured` |
| `ReasoningNodeType` | `input`, `process`, `decision`, `evidence`, `outcome`, `policy`, `action`, `risk`, `trust`, `confidence` |

---

## 8. Response Models — `src\q_guardian\response\data.py`

The Autonomous Response & Recovery Engine's models (module 9). Helper functions:
`_utcnow()` and `_uuid()` (used for all default timestamps and IDs).

| Group | Model | Key fields |
|-------|-------|------------|
| Inputs | `PolicyDecision` | `decision_id`, `outcome="allow"`, `action="allow"`, `severity="low"`, `risk_score=0.0`, `matched_rules=[]`, `reasoning=[]` |
| Inputs | `RiskAssessment` | `assessment_id`, `risk_score=0.0`, `risk_level="low"`, `threat_level="none"`, `confidence=1.0`, `severity="low"`, `contributing_sources=[]` |
| Inputs | `ActionPlan` | `plan_id`, `actions=[]`, `parameters={}`, `priority=0`, `timeout_seconds=30.0` |
| Response | `ResponseRequest` | `request_id`, `correlation_id`, `policy_decision=None`, `risk_assessment=None`, `action_plan=None`, `context={}` |
| Response | `ResponseResult` | `result_id`, `correlation_id=""`, `request_id=""`, `action=ResponseAction.ALLOW`, `status=PENDING`, `steps_executed=[]`, `steps_failed=[]`, `evidence_ids=[]`, `notification_ids=[]`, `quarantine_id=""`, `rollback_id=""`, `reasoning=[]`, `execution_time_ms=0.0` |
| Playbook | `PlaybookStep` | `step_id`, `name=""`, `step_type=ACTION`, `action=""`, `parameters={}`, `conditions=[]`, `timeout_seconds=30.0`, `retry_count=0`, `retry_delay_seconds=1.0`, `failure_strategy=STOP`, `depends_on=[]`, `on_success=""`, `on_failure=""`, `rollback_step=""`, `enabled=True` |
| Playbook | `PlaybookDefinition` | `playbook_id`, `name` (required), `description=""`, `version="1.0.0"`, `steps=[]`, `triggers=[]`, `conditions=[]`, `timeout_seconds=300.0`, `tags=[]`, `enabled=True`, `created_at`/`updated_at` |
| Playbook | `PlaybookExecution` | `execution_id`, `playbook_id=""`, `playbook_name=""`, `correlation_id=""`, `status=PENDING`, `step_results: list[StepResult]=[]`, `started_at=None`, `completed_at=None`, `execution_time_ms=0.0` |
| Playbook | `StepResult` | `step_id=""`, `step_name=""`, `status=PENDING`, `output=None`, `error=""`, `execution_time_ms=0.0`, `retry_count=0` |
| Quarantine | `QuarantineRecord` | `quarantine_id`, `correlation_id=""`, `target_type=AGENT`, `target_id=""`, `status=ACTIVE`, `reason=""`, `actions_blocked=[]`, `expires_at=None`, `released_at=None`, `released_by=""` |
| Evidence | `EvidenceRecord` | `evidence_id`, `correlation_id=""`, `evidence_type=CUSTOM`, `content={}`, `hash=""`, `immutable=True`, `created_at` |
| Evidence | `TimelineEvent` | `event_id`, `correlation_id=""`, `timestamp`, `event_type=""`, `source=""`, `description=""`, `data={}`, `severity="info"` |
| Evidence | `Timeline` | `timeline_id`, `correlation_id=""`, `events: list[TimelineEvent]=[]`, `created_at` |
| Notification | `NotificationRecord` | `notification_id`, `correlation_id=""`, `channel=LOG`, `priority=MEDIUM`, `subject=""`, `body=""`, `recipients=[]`, `status=""`, `sent_at=None`, `delivered=False`, `error=""` |
| Approval | `ApprovalRequest` | `request_id`, `correlation_id=""`, `approval_type=MANUAL`, `status=PENDING`, `action=""`, `description=""`, `context={}`, `approvers=[]`, `approvals_received=[]`, `required_approvals=1`, `timeout_seconds=300.0`, `resolved_at=None` |
| Rollback | `Checkpoint` | `checkpoint_id`, `correlation_id=""`, `target=CONFIGURATION`, `snapshot={}`, `description=""` |
| Rollback | `RollbackResult` | `rollback_id`, `correlation_id=""`, `checkpoint_id=""`, `target=CONFIGURATION`, `success=False`, `restored_state={}`, `error=""`, `execution_time_ms=0.0` |
| Recovery | `RecoveryPlan` | `plan_id`, `correlation_id=""`, `actions: list[RecoveryAction]=[]`, `parameters={}`, `priority=0`, `timeout_seconds=60.0` |
| Recovery | `RecoveryResult` | `result_id`, `correlation_id=""`, `plan_id=""`, `actions_attempted=[]`, `actions_succeeded=[]`, `actions_failed=[]`, `success=False`, `error=""`, `execution_time_ms=0.0` |
| Integration | `IntegrationConfig` | `integration_id`, `integration_type=CUSTOM`, `name=""`, `endpoint=""`, `api_key=""`, `enabled=True`, `settings={}` |
| Integration | `IntegrationResult` | `result_id`, `integration_id=""`, `integration_type=CUSTOM`, `status=""`, `correlation_id=""`, `request_id=""`, `success=False`, `response={}`, `response_data={}`, `error=""`, `execution_time_ms=0.0` |

Response enums live in `src\q_guardian\response\enums.py`: `ApprovalStatus`,
`ApprovalType`, `EvidenceType`, `IntegrationType`, `NotificationChannel`,
`NotificationPriority`, `QuarantineStatus`, `QuarantineType`, `RecoveryAction`,
`ResponseAction`, `ResponseStatus`, `RollbackTarget`, `StepStatus`, `StepType`,
`TimelineFormat`, `FailureStrategy` (17 total — see `src\q_guardian\response\enums.py`).

---

## 9. Observability Models — `src\q_guardian\observability\data.py`

The Observability platform's central models. All use `populate_by_name=True`.

### 9.1 Metrics

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `TimeWindow` | Query time range | `start`, `end`. Methods: `duration_seconds`, `contains(dt)` (inclusive). |
| `MetricPoint` | Single data point | `timestamp` (UTC), `value`, `labels={}` |
| `Metric` | Named metric | `metric_id`, `name`, `metric_type`, `unit=NONE`, `description=""`, `labels={}`, `points=[]`. Methods: `add_point()` (merges labels), `latest_value()`, `values_in_window(window)`. |
| `MetricSeries` | Aggregated series | `series_id`, `metric_name`, `aggregation="last"`, `interval_seconds=60`, `points=[]`, `labels={}` |
| `AggregatedMetric` | Aggregation result | `name`, `aggregation`, `value`, `count=0`, `min_value`/`max_value`, `labels={}`, `window=None` |

### 9.2 Health

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `HealthStatusModel` | Per-component health | `component`, `status=UNKNOWN`, `health_score=1.0` (0–1), `level=GOOD`, `last_heartbeat=None`, `uptime_seconds=0.0`, `warnings=[]`, `failures=[]`, `dependencies={}`. `update_level()` maps score→level (≥0.9 EXCELLENT, ≥0.7 GOOD, ≥0.5 FAIR, ≥0.3 POOR, else CRITICAL). |
| `HealthCheckResult` | One check outcome | `check_id`, `component`, `status`, `message=""`, `latency_ms=0.0`, `timestamp`, `details={}` |
| `HealthReport` | Aggregate report | `report_id`, `overall_status=UNKNOWN`, `overall_score=1.0`, `components=[]`, `timestamp`, `framework_uptime_seconds=0.0`, `active_warnings=0`, `active_failures=0`. `calculate_overall()` computes mean score + status precedence (UNHEALTHY > DEGRADED > HEALTHY; mixed → DEGRADED). |

### 9.3 Tracing

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `SpanStatus` | Status code carrier | `code=0` (0=OK,1=ERROR,2=TIMEOUT), `message=""`. Classmethods: `ok()`, `error()`, `timeout()`. |
| `Span` | Single span | `span_id`, `trace_id`, `parent_span_id=None`, `name`, `kind=INTERNAL`, `start_time`, `end_time=None`, `status=ok()`, `attributes={}`, `events=[]`, `labels={}`. Properties: `duration_ms`, `is_complete`. Methods: `finish()`, `add_event()`, `set_attribute()`. |
| `Trace` | Distributed trace | `trace_id`, `correlation_id=""`, `execution_id=""`, `status=ACTIVE`, `start_time`/`end_time`, `spans=[]`, `labels={}`, `metadata={}`. Properties: `duration_ms`, `span_count`. Methods: `add_span()`, `get_span()`, `get_root_spans()`, `get_child_spans()`, `finish()`. |

### 9.4 Alerts

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `AlertRule` | Alert rule definition | `rule_id`, `name`, `description=""`, `alert_type=THRESHOLD`, `severity=MEDIUM`, `metric_name`, `condition` (`gt`/`lt`/`eq`/`gte`/`lte`), `threshold`, `duration_seconds=0`, `labels={}`, `annotations={}`, `enabled=True`, `cooldown_seconds=300`. Method: `evaluate(value)` (dispatch table of lambdas). |
| `Alert` | Active/resolved alert | `alert_id`, `rule_id`, `rule_name=""`, `state=PENDING`, `severity=MEDIUM`, `alert_type=THRESHOLD`, `message=""`, `labels/annotations`, `created_at`/`updated_at`, `resolved_at=None`, `acknowledged_at=None`, `acknowledged_by=None`, `evaluation_value=None`, `escalation_level=0`. Properties/methods: `duration_seconds`, `acknowledge()`, `resolve()`, `escalate()` (state→ESCALATED), `suppress()`. |
| `AlertEvent` | State-change event | `event_id`, `alert_id`, `old_state=None`, `new_state`, `timestamp`, `message=""`, `metadata={}` |

### 9.5 Analytics & Runtime Snapshot

| Model | Purpose | Key fields |
|-------|---------|-----------|
| `TrendData` | Trend analysis result | `metric_name`, `direction`, `slope=0.0`, `r_squared=0.0`, `mean=0.0`, `std_dev=0.0`, `min_value`/`max_value=0.0`, `sample_count=0`, `period=None` |
| `ForecastResult` | Forecast output | `metric_name`, `forecast_values=[]`, `confidence_interval_lower/upper=[]`, `method="linear"`, `confidence_level=0.95` |
| `AnalyticsReport` | Comprehensive report | `report_id`, `title="Analytics Report"`, `generated_at`, `time_window=None`, `threat_trends`/`policy_trends`/`risk_trends`/`response_trends`, `provider_accuracy={}`, `plugin_usage`/`quantum_usage`/`fusion_strategy_usage={}`, `average_confidence`, `top_threat_types`/`top_policies`/`most_active_sessions`/`most_active_agents`, `forecasts=[]`, `summary={}` |
| `RuntimeStatistics` | Runtime snapshot | `timestamp`, `total_requests`/`active_requests`, `requests_per_second`, `total_sessions`/`active_sessions`, `total_agents`/`active_agents`, `total_threats_detected`, `threats_per_second`, `blocked_requests`/`allowed_requests`, `quarantined_count`, `success_rate`/`failure_rate`/`recovery_rate` |
| `PerformanceMetrics` | Latency breakdown | `timestamp`, `prompt_latency_ms`/`detection_latency_ms`/`fusion_latency_ms`/`quantum_latency_ms`/`ml_latency_ms`/`policy_latency_ms`/`response_latency_ms`, `average_execution_time_ms`/`peak_execution_time_ms`, `plugin_execution_times={}`, `p50_latency_ms`/`p95_latency_ms`/`p99_latency_ms` |
| `ResourceMetrics` | Resource utilization | `timestamp`, `queue_size`/`max_queue_size`, `active_workers`/`max_workers`, `memory_usage_bytes`, `cpu_usage_percent`, `open_connections`, `file_descriptors` |
| `DashboardSnapshot` | Full dashboard snapshot | `snapshot_id`, `timestamp`, `runtime_stats`, `performance`, `resources`, `health`, `recent_alerts=[]`, `active_alerts_count=0`, `top_metrics=[]`, `metadata={}` |

Observability enums live in `src\q_guardian\observability\enums.py`: `MetricType`,
`MetricUnit`, `HealthStatus`, `HealthLevel`, `AlertSeverity`, `AlertState`,
`AlertType`, `TraceStatus`, `SpanKind`, `AnalyticsGranularity`, `ExporterType`,
`DashboardFormat`, `AggregationType`, `PercentileType`, `TrendDirection`,
`RollupInterval`.

---

## 10. Framework Models

The framework layer (`src\q_guardian\framework\`) contributes its own small model set:

| Model | Location | Purpose |
|-------|----------|---------|
| `FrameworkConfig` | `framework\config.py` | Global framework settings consumed by the `Guardian` SDK facade |
| `FrameworkContext` | `framework\context.py` | Runtime context carrying event bus, plugin registry, hook manager, runtime state, and managers across the lifecycle |
| `FrameworkState` | `framework\state.py` | Explicit lifecycle state machine values (`init`, `starting`, `running`, `stopping`, `stopped`) |
| `RuntimeContext` | `runtime\context.py` | Runtime-side context wrapper over `runtime.models` objects |

The top-level `q_guardian/__init__.py` re-exports these alongside the module model
sets listed above, giving users a single import surface:
`Guardian`, `FrameworkConfig`, `FrameworkContext`, `FrameworkState`, `Event`,
`EventBus`, `Plugin`, `PluginRegistry`, `HookManager`, `Adapter`, and the
runtime/security/ml/quantum/policy/risk/response/observability model namespaces.

---

## 11. Cross-Module Contract Summary

| Producer | Model handed off | Consumer | Notes |
|----------|------------------|----------|-------|
| security pipeline | `PromptAnalysis` | decision engine, risk plugin, ML plugin | `to_security_dict()` is the JSON contract for external callers |
| ML models | `InferenceResult` | fusion strategies, risk `NormalizedPrediction` | carries `findings: list[PromptFinding]` |
| quantum inference | `QuantumInferenceResult` | fusion strategies, risk | legacy `FusedResult` vs Phase-3 `FusedPrediction` |
| fusion | `FusedPrediction` | risk `NormalizedPrediction` (`source_type="fused"`) | single normalization point |
| risk engine | `RiskAssessment` | policy engine, `RiskAnalysisPlugin.assess()` | primary risk artifact |
| risk policy | `PolicyDecision` | action engine, response engine | response has its own `PolicyDecision` input model |
| response engine | `ResponseResult` | quarantine, notifications, evidence, integrations | aggregated outcome with correlation_id |
| policy engine | `PolicyEvaluationResult` | callers of `AdvancedPolicyEngine.evaluate()` | includes winning + all matching rules |
| observability | `Metric`, `Trace`, `Span`, `Alert`, `HealthReport`, `DashboardSnapshot` | storage, exporters, dashboard API | `correlation_id` ties traces to response/request models |

**Conventions to rely on when writing code:**

- Every ID is a UUID string (see `utils/uuid_utils.py:generate_uuid`).
- Every timestamp is UTC (`datetime.now(UTC)`).
- Every severity/status/type is a `str` enum — compare with the enum, not raw strings.
- Models tolerate extra fields only where `extra="allow"` (e.g.
  `PromptSecurityConfig`); the rest are strict to field definitions.
- `populate_by_name=True` is the universal config — prefer keyword-safe construction.
