# 16 - Autonomous Response & Recovery

> Module: `src\q_guardian\response\` ("Module 9"). Source-agnostic response orchestration
> for AI-agent security incidents. It consumes `PolicyDecision` / `RiskAssessment` /
> `ActionPlan` inputs and produces `ResponseResult` outputs — it knows nothing about
> rule engines, ML, quantum, or fusion.

---

## 1. Architecture Overview

```
 PolicyDecision / RiskAssessment / ActionPlan   (source-agnostic inputs)
        │
        ▼
   ResponseEngine ──────► ResponseResult
        │
        ├── OrchestrationEngine ── executes Playbooks (step-by-step, deps, failure strategies)
        ├── RecoveryEngine       ── executes RecoveryPlan (7 default recovery actions)
        ├── RollbackEngine       ── checkpoint-based rollback (policy/session/plugin/config/runtime)
        ├── ApprovalEngine       ── auto/manual/multi-level/quorum approvals
        │
        ├── Evidence  : EvidenceCollector, EvidenceSnapshot, EvidenceTimeline
        ├── Quarantine: QuarantineManager + session/agent/plugin/memory wrappers
        ├── Notify    : Notifier + Email/Webhook/Slack/Teams handlers
        ├── Integrate : Sentinel / Splunk / QRadar / Cortex / ServiceNow (SOAR stubs)
        └── Persist   : ResponseStorage (JSON per category), Playbook registry/parser/validator
```

The package is **self-contained**: no production code outside `src\q_guardian\response\`
imports it (consumed by `tests\response\`).

---

## 2. Enums (all `str, Enum`, lowercase values)

| Enum | Members |
|---|---|
| `ResponseAction` | allow, block, warn, quarantine, terminate, escalate, monitor, manual_approval, delayed_action, retry, rollback, log_only, notify, isolate, restore |
| `ResponseStatus` | pending, in_progress, completed, failed, cancelled, waiting_approval, rolled_back, timed_out, partial |
| `StepStatus` | pending, running, completed, failed, skipped, waiting, rolled_back, timed_out |
| `StepType` | action, condition, parallel, approval, wait, rollback, notification, evidence, branch, sub_playbook |
| `QuarantineType` | agent, session, plugin, memory, tool, full |
| `QuarantineStatus` | active, expired, manually_released, auto_released, escalated |
| `EvidenceType` | prompt, runtime_context, threat_prediction, fusion_output, risk_assessment, policy_decision, action_result, timeline, plugin_state, system_state, custom |
| `NotificationChannel` | email, webhook, slack, teams, pagerduty, discord, log, sms |
| `NotificationPriority` | low, medium, high, critical |
| `ApprovalType` | automatic, manual, multi_level, timeout, quorum |
| `ApprovalStatus` | pending, approved, rejected, expired, cancelled |
| `IntegrationType` | sentinel, splunk, qradar, cortex_xsoar, servicenow, custom |
| `RollbackTarget` | policy, session, plugin, configuration, runtime, full |
| `RecoveryAction` | resume_session, restore_runtime, restore_plugins, restore_memory, retry_request, restore_policy, restart_agent, custom |
| `TimelineFormat` | json, markdown, html, csv |
| `FailureStrategy` | stop, continue, retry, rollback, skip, escalate |

---

## 3. Core Engines — `response\engine\`

### 3.1 `ResponseEngine.process(request)` — action resolution

1. Idempotency check: if enabled and `request.request_id` already cached → return cached
   `ResponseResult` (logs `response_idempotent_hit`).
2. Resolve action by **priority**:
   `action_plan.actions[0]` > `policy_decision.action` > `risk_assessment` > `ALLOW`
   (reasoning: "No inputs provided, defaulting to ALLOW").
3. Build result with `status=COMPLETED`, store by `correlation_id`, cache by `request_id`.

**`_ACTION_MAP`** (policy action string → `ResponseAction`): `allow`, `block`, `warn`,
`quarantine`, `terminate`, `escalate`, `monitor`, `manual_approval`, `delayed_action`,
`retry`, `rollback`, `log`/`log_only` → LOG_ONLY, `notify`, `isolate`, `restore`.
Unknown strings → `ALLOW`.

**`_risk_to_action(risk_assessment)`**: `critical` risk/threat → `BLOCK`;
`severe`/`high` risk or `high` threat → `ESCALATE`; `moderate` risk or `medium` threat →
`WARN`; otherwise → `ALLOW`.

### 3.2 `OrchestrationEngine.execute_playbook(playbook, context)` — step loop

- Skips disabled steps; **dependency check** — unmet `depends_on` → `StepResult(SKIPPED,
  error="Unmet dependencies: ...")`.
- Merged context: `{**context, **step_outputs, "_correlation_id": cid}`.
- On step failure, applies `failure_strategy`:
  `stop` → FAILED + break · `rollback` → ROLLED_BACK + break · `skip` → continue ·
  `retry` → up to `retry_count` attempts (final error `"Retry {n}/{max} failed"`) ·
  anything else → continue.
- Final status: `COMPLETED` if no failures else `PARTIAL` (when still in-progress).
- Custom step handlers: `register_handler(step_type, handler)`; default action handler
  returns `{"action": ..., "parameters": ...}`.

### 3.3 `RecoveryEngine` — 7 default recovery handlers (logging-only stubs)

| Action | Handler | Returns |
|---|---|---|
| resume_session | `_handle_resume_session` | `{"resumed": True, "session_id": ...}` |
| restore_runtime | `_handle_restore_runtime` | `{"restored": True}` |
| restore_plugins | `_handle_restore_plugins` | `{"restored": True, "plugins": [...]}` |
| restore_memory | `_handle_restore_memory` | `{"restored": True}` |
| retry_request | `_handle_retry_request` | `{"retried": True, "request_id": ...}` |
| restore_policy | `_handle_restore_policy` | `{"restored": True, "version": ...}` |
| restart_agent | `_handle_restart_agent` | `{"restarted": True, "agent_id": ...}` |

`CUSTOM` has no default handler. Each action retried up to `max_attempts` (default 3);
missing handler → added to `failed`. `success = len(failed) == 0`. In production these
stubs would call real systems.

### 3.4 `RollbackEngine` — checkpoint-based rollback

- `create_checkpoint(target, state, ...)` — stores `snapshot=state.copy()`; caps at
  `max_checkpoints=50` per target (drops oldest).
- `rollback(checkpoint_id)` → success with `restored_state=snapshot.copy()`; missing →
  `success=False, error="Checkpoint not found: ..."`.
- `rollback_latest(target)` — most recent checkpoint for the target.

### 3.5 `ApprovalEngine` — approval workflows

- `request_approval(...)` — `AUTOMATIC` type auto-approves (`approvals_received=["system"]`).
- `approve(request_id, approver)` — raises `ApprovalError` if not PENDING; approved when
  `len(approvals_received) >= required_approvals` (quorum = counted approvals).
- `reject(...)` / `cancel(...)` / `check_timeouts()` (→ EXPIRED) are the resolution paths.
- Defaults: `default_timeout_seconds=300.0`. Config `require_approval_for` defaults to
  `["terminate", "rollback", "quarantine"]`.

---

## 4. Evidence — `response\evidence\`

- **`EvidenceCollector`** — in-memory records: `collect(type, source, data, ...)`; lookups
  by id / correlation_id / type; `count()`, `clear()`.
- **`EvidenceSnapshot`** — `capture(name, state, ...)` records `EvidenceType.SYSTEM_STATE`
  with `metadata={"snapshot_name": name}`.
- **`EvidenceTimeline`** — `create_timeline`, `add_event` (severity order
  `debug<info<warning<error<critical`), `export_timeline` in `JSON` / `MARKDOWN` / `CSV`
  (`HTML` enum member exists but is **not supported** — raises `EvidenceError`).
  - JSON: `{"timeline_id", "events": [...]}` (indent 2).
  - TEXT/Markdown: `"[{ISO}] [{SEVERITY}] {event_type} | {source}"`.
  - CSV: header `timestamp,event_type,source,severity`.

---

## 5. Quarantine — `response\quarantine\`

**`QuarantineManager`** (defaults: `default_duration_seconds=3600`, `max_duration_seconds=86400`):

- `quarantine(type, target_id, ..., duration)` — duration capped at max; `expires_at =
  now + duration`.
- `release(...)` — requires ACTIVE else `QuarantineError`; sets `MANUALLY_RELEASED`.
- `check_expired()` — **auto-release** past-expiry records (`AUTO_RELEASED`,
  `released_by="system-auto-release"`).
- `is_quarantined(type, target_id)` — true if an ACTIVE record matches.

Convenience wrappers block specific actions: `SessionQuarantine` →
`["send_message","execute_tool","access_memory"]`; `AgentQuarantine` → `["all"]`;
`PluginQuarantine` → `["execute","communicate"]`; `MemoryQuarantine` →
`["read","write","delete"]`.

---

## 6. Playbooks — `response\playbooks\`

- **`PlaybookParser`** — `parse_yaml_like` (minimal line-based YAML: no nested maps),
  `parse_json`, `parse_dict`. Step key aliases: `type`→`step_type`, `timeout`→`timeout_seconds`,
  `retry`→`retry_count`, `failure`→`failure_strategy`, `rollback`→`rollback_step`.
- **`PlaybookValidator`** — errors: missing name / zero steps / >100 steps / duplicate
  step names or ids / bad `depends_on` refs / negative timeouts/retries. `require_valid`
  raises `PlaybookValidationError`.
- **`PlaybookRegistry`** — register / unregister / get / `get_by_trigger` /
  `list_enabled`. Duplicate `playbook_id` → `PlaybookError`.
- **`PlaybookExecutor`** — rejects disabled playbooks or empty steps; `execute_by_trigger`
  looks up via `registry.get_by_trigger`; delegates to `OrchestrationEngine`.

### 6.1 Built-in playbooks (`BUILTIN_PLAYBOOKS`)

| Name | Triggers | Step chain |
|---|---|---|
| `block-threat` | threat_detected, prompt_injection, jailbreak | collect-evidence → quarantine-target → block-session → notify-admin → generate-report |
| `quarantine-agent` | suspicious_behavior, anomaly_detected | collect-evidence → quarantine-agent → **request-approval** (APPROVAL, timeout=600) → notify-team |
| `escalate-incident` | high_severity, critical_risk | collect-evidence → escalate → notify-ops (channel=pagerduty, priority=critical) → create-ticket |
| `rollback-operation` | deployment_failed, policy_error | capture-state → rollback → verify-restore → notify |

---

## 7. Notifications & Integrations

**`Notifier`** routes to registered channel handlers (each must expose
`send_notification(recipients, subject, body, priority)`). Never raises — no handler →
record with `error="No handler registered for channel ..."`; handler exception → `status="failed"`.

| Handler | Defaults / notes |
|---|---|
| `EmailNotifier` | `smtp_config` dict; result `{"channel":"email", ...}` |
| `WebhookNotifier` | `url`, `headers`; result `{"channel":"webhook", "url": ...}` |
| `SlackNotifier` | `webhook_url`, `channel="#security"`; result `{"channel":"slack", "slack_channel": ...}` |
| `TeamsNotifier` | `webhook_url`; result `{"channel":"teams", ...}` |

**SOAR integrations** (all **stub/mock** — build & store `IntegrationResult`, no network):

| Integration | Methods |
|---|---|
| `SentinelIntegration` | `send_incident`, `send_alert` |
| `SplunkIntegration` | `send_event`, `send_alert` |
| `QRadarIntegration` | `send_offense`, `send_event` |
| `CortexIntegration` | `create_case`, `run_analyzer` |
| `ServiceNowIntegration` | `create_incident`, `create_change_request` |

---

## 8. Plugins & Storage

- **`ResponsePlugin`** — base: `name`, `version`, `initialize(config)`, `shutdown()`,
  `can_handle(action)` (default False), `execute(action, context)` (raises
  `NotImplementedError`), `is_initialized`.
- **`PluginRegistry`** — `register(plugin, config)` (initializes + stores by name),
  `unregister(name)`, `bind_action(action, plugin_name)` (raises `ValueError` if missing),
  `get_handler(action)`, `shutdown_all()`.
- **`ResponseStorage`** — JSON persistence under `response_storage/` with six subdirs:
  `responses/`, `quarantines/`, `playbooks/`, `evidence/`, `recovery/`, `rollbacks/`;
  save/load per category, `list_*` by stem, `delete(category, id)`, `_serialize` uses
  `model_dump(mode="json")`.

---

## 9. Events (audit/tracking, all extend `ResponseEvent`)

`ResponseInitiated`, `ResponseCompleted`, `ResponseFailed`, `PlaybookStarted`,
`PlaybookCompleted`, `PlaybookStepCompleted`, `PlaybookStepFailed`, `QuarantineActivated`,
`QuarantineReleased`, `EvidenceCollected`, `NotificationSent`, `ApprovalRequested`,
`ApprovalResolved`, `RollbackInitiated`, `RollbackCompleted`, `RecoveryInitiated`,
`RecoveryCompleted`, `IntegrationCalled`, `IntegrationCompleted` (20 concrete events).
Currently emitted for audit/integration use (not instantiated by engine code).

---

## 10. Configuration Highlights (`ResponseEngineConfig`)

| Area | Defaults |
|---|---|
| Response | `default_timeout_seconds=30`, `max_concurrent_responses=10`, idempotency on, `default_failure_strategy=STOP` |
| Playbooks | `playbook_directory="playbooks/"`, `max_playbook_steps=100`, `playbook_timeout_seconds=300` |
| Quarantine | `default_quarantine_duration_seconds=3600`, `max=86400`, auto-release on (check every 60 s) |
| Evidence | immutable on, `evidence_storage_path="evidence/"`, 10 MB max, 90-day retention |
| Notifications | `enabled_channels=[LOG]`, timeout 10 s, max 3 retries |
| Approval | `timeout=300`, requires approval for `["terminate","rollback","quarantine"]` |
| Recovery | auto-recovery on, `max_recovery_attempts=3`, delay 5 s |
| Rollback | checkpointing on, `max_checkpoints=50` |
| Storage | `persist_responses=False`, `storage_path="response_store.json"` |

---

## 11. Quick Start

```python
from q_guardian.response import ResponseEngine, PlaybookExecutor, BUILTIN_PLAYBOOKS
from q_guardian.response.data import ResponseRequest, PolicyDecision

engine = ResponseEngine()                      # configurable via ResponseEngineConfig

# Direct decision → result
req = ResponseRequest(policy_decision=PolicyDecision(
    outcome="blocked", action="block", severity="high", risk_score=0.85))
result = engine.process(req)                   # action == ResponseAction.BLOCK

# Execute a built-in playbook
executor = PlaybookExecutor()
playbook = BUILTIN_PLAYBOOKS["block-threat"]()
execution = executor.execute(playbook, {"target_id": "agent-7"}, correlation_id="abc")
```

---

## 12. Dependency Map

- `enums.py` ← everything (data, config, engines, evidence, notifications, integrations,
  playbooks, quarantine, plugin).
- `data.py` ← engines, storage, evidence, notifier, integrations, playbooks, quarantine.
- `config.py` ← `response_engine.py`.
- `orchestration_engine.py` ← `playbooks\executor.py` (instantiates one).
- `quarantine_manager.py` ← session / agent / plugin / memory wrappers.
- Package `__init__.py` re-exports the public API of every subpackage (90+ names:
  17 enums, 22 data models, 21 events, 13 exceptions, 5 engines, playbook system,
  quarantine, evidence, notifications, integrations, plugin & storage).
- Exceptions root: `ResponseEngineError` (carries `details` dict) → `PlaybookError`,
  `PlaybookValidationError`, `QuarantineError`, `EvidenceError`, `NotificationError`,
  `ApprovalError`, `RollbackError`, `RecoveryError`, `IntegrationError`,
  `OrchestrationError`, `TimeoutError` (exported as `ResponseTimeoutError`),
  `CorrelationError`.
