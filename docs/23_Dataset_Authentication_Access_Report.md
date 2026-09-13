# Dataset Authentication & Access Verification Report

> Generated: 2026-09-06  
> Scope: Q-Guardian DatasetRegistry — HuggingFace authenticated dataset access validation

## Overview

This report documents the authenticated access verification for all datasets registered in
the Q-Guardian `DatasetRegistry`. It covers the authentication resolution mechanism, dataset
classification, access-check results, and security validation of the token-handling pipeline.

---

## 1. Dataset Registry

The `DatasetRegistry` (`src/q_guardian/benchmark/registry.py`) defines **11 datasets** via
`DatasetSpec` entries. Datasets are classified by the `requires_token` field on each spec.

### 1.1 Public Datasets (3)

No HuggingFace token required. Directly accessible.

| Dataset ID | Source (HF Repo) | License | Homepage |
| --- | --- | --- | --- |
| `deepset-prompt-injections` | `deepset/prompt-injections` | Apache-2.0 | https://huggingface.co/datasets/deepset/prompt-injections |
| `jbb-behaviors` | `JailbreakBench/JBB-Behaviors` | public | https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors |
| `dolly-benign` | `databricks/databricks-dolly-15k` | CC BY-SA 3.0 | https://huggingface.co/datasets/databricks/databricks-dolly-15k |

### 1.2 Gated Datasets (8)

Registered with `requires_token=True`; HuggingFace access control applies (terms,
approval, or private-repo mechanics vary by dataset — this cannot be determined from
registry metadata alone).

| Dataset ID | Source (HF Repo) | License | Homepage |
| --- | --- | --- | --- |
| `jailbreakbench-attacks` | `JailbreakBench/JBB-Attacks` | public | https://huggingface.co/datasets/JailbreakBench/JBB-Attacks |
| `wildjailbreak` | `allenai/wildjailbreak` | MIT | https://huggingface.co/datasets/allenai/wildjailbreak |
| `harmbench-behaviors` | `cais/harmbench_behaviors` | research-only | https://huggingface.co/datasets/cais/harmbench_behaviors |
| `advbench` | `DeepMind/AdvBench` | research-only | https://huggingface.co/datasets/DeepMind/AdvBench |
| `hex-phi` | `walledai/HEx-PHI` | research-only | https://huggingface.co/datasets/walledai/HEx-PHI |
| `pal` | `ProtectAI/PAL` | research-only | https://huggingface.co/datasets/ProtectAI/PAL |
| `agentdojo` | `ibm/agentdojo` | CC BY 4.0 | https://huggingface.co/datasets/ibm/agentdojo |
| `cyberseceval-prompt-injections` | `facebook/CyberSecEval-PromptInjections` | research-only | https://huggingface.co/datasets/facebook/CyberSecEval-PromptInjections |

---

## 2. Authentication Resolution

### 2.1 Token Resolution Priority

Implemented in `cli.py:_resolve_token()` and `auth.py:AuthConfig`:

1. `HF_TOKEN` environment variable (highest priority)
2. `--hf-token` CLI argument (stored as `SecretStr` in `TrainingPipelineConfig`)
3. `hf_token` in config JSON file (masked as `***` in serialized artifacts)

### 2.2 Auth System Components

| Component | Location | Role |
| --- | --- | --- |
| `AuthConfig` | `src/q_guardian/ml/datasets/auth.py` | Resolves token from env/config |
| `DatasetAuthResolver` | `src/q_guardian/ml/datasets/auth.py` | Classifies access, validates token, builds auth headers |
| `DatasetAccessType` | `src/q_guardian/ml/datasets/auth.py` | Enum: PUBLIC, AUTHENTICATED, GATED, PRIVATE, UNAVAILABLE, INVALID |
| `DatasetAccessInfo` | `src/q_guardian/ml/datasets/auth.py` | Frozen dataclass with access classification + guidance message |
| `create_auth_resolver()` | `src/q_guardian/ml/datasets/auth.py` | Factory function for resolver creation |

### 2.3 Verification Results

| Check | Result |
| --- | --- |
| `HF_TOKEN` env var detected | YES |
| Token format valid (`hf_` prefix, length >= 20) | YES |
| `AuthConfig.from_env()` resolves token | YES |
| `DatasetAuthResolver.has_token` returns True | YES |
| `create_auth_resolver(token)` factory works | YES |

---

## 3. Access Check Results

### 3.1 Offline Registry Classification

Via `q-guardian dataset check-access --offline`:

| Dataset ID | Classification |
| --- | --- |
| `deepset-prompt-injections` | PUBLIC |
| `jbb-behaviors` | PUBLIC |
| `dolly-benign` | PUBLIC |
| `jailbreakbench-attacks` | GATED (token required; access not confirmed) |
| `wildjailbreak` | GATED (token required; access not confirmed) |
| `harmbench-behaviors` | GATED (token required; access not confirmed) |
| `advbench` | GATED (token required; access not confirmed) |
| `hex-phi` | GATED (token required; access not confirmed) |
| `pal` | GATED (token required; access not confirmed) |
| `agentdojo` | GATED (token required; access not confirmed) |
| `cyberseceval-prompt-injections` | GATED (token required; access not confirmed) |

### 3.2 Online Hub API Verification

Verified via HuggingFace Hub API (`https://huggingface.co/api/datasets/{source}`) with the
configured token. HTTP 404 from the Hub API is deliberately ambiguous: HuggingFace hides
gated/private repositories from tokens that have not been granted access, so a 404 does
**not** by itself prove that manual terms acceptance is the block. Interpretation is
therefore conservative.

| Dataset ID | HF API Response | Interpretation |
| --- | --- | --- |
| `deepset-prompt-injections` | 200 OK (`gated=False`) | Public — fully accessible |
| `jbb-behaviors` | 200 OK (`gated=False`) | Public — fully accessible |
| `dolly-benign` | 200 OK (`gated=False`) | Public — fully accessible |
| `jailbreakbench-attacks` | 404 Not Found | Access could not be confirmed |
| `wildjailbreak` | 200 OK (`gated=auto`) | Repo visible + token recognized; row-level access not confirmed |
| `harmbench-behaviors` | 404 Not Found | Access could not be confirmed |
| `advbench` | 404 Not Found | Access could not be confirmed |
| `hex-phi` | 404 Not Found | Access could not be confirmed |
| `pal` | 404 Not Found | Access could not be confirmed |
| `agentdojo` | 404 Not Found | Access could not be confirmed |
| `cyberseceval-prompt-injections` | 404 Not Found | Access could not be confirmed |

### 3.3 Consolidated Results Table

| Dataset | Exact Dataset ID | Access Classification | Access Result | HF API Response | Notes |
| --- | --- | --- | --- | --- | --- |
| deepset/prompt-injections | `deepset-prompt-injections` | Public | Accessible | 200 OK (gated=False) | Public, no token required |
| JBB-Behaviors | `jbb-behaviors` | Public | Accessible | 200 OK (gated=False) | Public, no token required |
| databricks-dolly-15k | `dolly-benign` | Public | Accessible | 200 OK (gated=False) | Public, no token required |
| JBB-Attacks | `jailbreakbench-attacks` | Gated | Access Not Confirmed | 404 Not Found | Repo hidden from token; cause ambiguous |
| WildJailbreak | `wildjailbreak` | Gated | Repo visible, access not confirmed | 200 OK (gated=auto) | No row-level confirmation |
| HarmBench Behaviors | `harmbench-behaviors` | Gated | Access Not Confirmed | 404 Not Found | Repo hidden from token; cause ambiguous |
| AdvBench | `advbench` | Gated | Access Not Confirmed | 404 Not Found | Repo hidden from token; cause ambiguous |
| HEx-PHI | `hex-phi` | Gated | Access Not Confirmed | 404 Not Found | Repo hidden from token; cause ambiguous |
| PAL | `pal` | Gated | Access Not Confirmed | 404 Not Found | Repo hidden from token; cause ambiguous |
| AgentDojo | `agentdojo` | Gated | Access Not Confirmed | 404 Not Found | Repo hidden from token; cause ambiguous |
| CyberSecEval-PromptInjections | `cyberseceval-prompt-injections` | Gated | Access Not Confirmed | 404 Not Found | Repo hidden from token; cause ambiguous |

---

## 4. Official Dataset Pages

All URLs derived from the `homepage` field in each `DatasetSpec` registered by Q-Guardian.

| Dataset ID | Official HuggingFace Dataset Page |
| --- | --- |
| `deepset-prompt-injections` | https://huggingface.co/datasets/deepset/prompt-injections |
| `jbb-behaviors` | https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors |
| `dolly-benign` | https://huggingface.co/datasets/databricks/databricks-dolly-15k |
| `jailbreakbench-attacks` | https://huggingface.co/datasets/JailbreakBench/JBB-Attacks |
| `wildjailbreak` | https://huggingface.co/datasets/allenai/wildjailbreak |
| `harmbench-behaviors` | https://huggingface.co/datasets/cais/harmbench_behaviors |
| `advbench` | https://huggingface.co/datasets/DeepMind/AdvBench |
| `hex-phi` | https://huggingface.co/datasets/walledai/HEx-PHI |
| `pal` | https://huggingface.co/datasets/ProtectAI/PAL |
| `agentdojo` | https://huggingface.co/datasets/ibm/agentdojo |
| `cyberseceval-prompt-injections` | https://huggingface.co/datasets/facebook/CyberSecEval-PromptInjections |

---

## 5. Security Validation

### 5.1 Token Exposure Checks

| Check | Status | Detail |
| --- | --- | --- |
| Token not printed in full output | PASS | CLI reports only `Configured: YES/NO`; the 8-character preview was removed |
| No token fragment in output | PASS | `authenticate-status` prints no prefix/suffix/substring |
| Token not in git diff | PASS | All `hf_` references are env var names, placeholders, or format checks |
| Token not in logs/exceptions | PASS | `get_auth_headers()` is used only in HTTP requests, never logged |
| Token not in config artifacts | PASS | `SecretStr` type masks as `***` in serialized configs |
| Token not written to files | PASS | No new files created during verification session |

### 5.2 `git status` Confirmation

```
On branch main — up to date with 'origin/main'
```

Pre-existing staged changes: 3 renamed test files. Pre-existing unstaged modifications to
source, docs, and tests. **No new untracked files were created by this verification.**
No secrets have entered the working tree.

---

## 6. Follow-up Fixes (2026-09-06)

### 6.1 `check_dataset_access` Online Mode Classification Bug — FIXED

**Confirmed defect.** When `allow_offline=False`, `check_dataset_access()` in
`auth.py` returned `AUTHENTICATED` for **all** HuggingFace datasets whenever a token was
present, ignoring `spec.requires_token`. The fall-through return at the old line 284
misclassified genuinely public datasets as authentication-required.

**Fix:** The online path now tests `spec.requires_token` before classifying: a public HF
dataset stays `PUBLIC` (`requires_token=False`), a token-less gated dataset is `GATED`,
and a gated dataset with a token configured is `AUTHENTICATED`. Online and offline
classification now agree. Regression tests cover public/no-token, public/with-token,
gated/no-token, and gated/with-token across both modes.

- `src/q_guardian/ml/datasets/auth.py` — `DatasetAuthResolver.check_dataset_access()`
- `tests/unit/test_dataset_auth.py` — online classification regression tests
- `tests/unit/test_cli_dataset_auth.py` — CLI online access-check regression tests

### 6.2 Token Partial Exposure — FIXED

**Confirmed defect.** `cli.py:_cmd_dataset_auth_status()` printed a short prefix of the
real token followed by `...`. No portion of the token may be displayed unnecessarily.

**Fix:** The `Token preview:` line was removed. The command now reports only safe status
(`Configured: YES/NO`, `Format valid: YES/NO`) plus the `HF_TOKEN` source priority and
security notes. A regression test asserts that zero token fragments appear in CLI output.

- `src/q_guardian/cli.py` — `_cmd_dataset_auth_status()`
- `tests/unit/test_cli_dataset_auth.py` — `test_auth_status_never_exposes_token_fragments`

### 6.3 Gated Dataset HTTP 404 Interpretation — CORRECTED

The earlier report read HTTP 404 as "terms acceptance required". A 404 from the Hub API is
ambiguous: HuggingFace intentionally hides inaccessible gated/private repositories from
unauthorized tokens, so a 404 may mean gated-without-access, private, a changed repository
identifier, or an unavailable repository. The revised interpretation is conservative —
**"Access Could Not Be Confirmed"** — unless explicit metadata states otherwise.

### 6.4 `wildjailbreak` Access Validation — CORRECTED

The earlier report described `wildjailbreak` as "likely accessible". Distinctions:

1. **Repository visible** — YES (Hub API 200)
2. **Token recognized** — YES (authenticated request returns 200)
3. **Dataset marked `gated=auto`** — YES
4. **Actual row-level dataset access confirmed** — NO

Row-level access could not be confirmed because the `datasets-server` API (used by
`DatasetDownloader`) returns 404 for gated datasets, and the optional `datasets` library
(the `HuggingFaceLoader` path) is not installed in this environment. Do not classify this
dataset as fully accessible on metadata alone.

### 6.5 Datasets-Server Limitation

The `datasets-server.huggingface.co` API (used by `DatasetDownloader` for row-level downloads)
returns HTTP 404 for all gated datasets regardless of token. This is a known HuggingFace
infrastructure limitation — the server only indexes public datasets for row access.

---

## 7. Summary

| Metric | Count |
| --- | --- |
| Total datasets discovered | 11 |
| Public datasets | 3 |
| Gated datasets | 8 |
| Accessible (confirmed via API) | 3 public |
| Repo visible, access not confirmed | 1 (`wildjailbreak`) |
| Access not confirmed (ambiguous 404) | 7 |
| Token configured successfully | YES |
| Token recognized by auth system | YES |
| Actual dataset access granted (confirmed) | 3 public; 8 not confirmed |

### Distinction: Token Status vs Access Status

A successful token check does **not** mean access has been granted to every gated dataset.
The following distinctions apply:

1. **Token configured successfully** — `HF_TOKEN` env var is set and detected
2. **Token recognized by the authentication system** — format valid, resolver functional
3. **Repository visible with the token** — Hub API metadata accessible (e.g. `wildjailbreak`)
4. **Dataset access has actually been granted** — confirmed via a real access/row probe

No claim of authenticated access is made for gated datasets unless the repository's actual
access mechanism confirms it.

---

## 8. CLI Commands Used

```bash
# Verify token configuration
q-guardian dataset authenticate-status

# Offline registry classification (no network)
q-guardian dataset check-access --offline <dataset_id> [<dataset_id> ...]

# Online access verification (network + token)
q-guardian dataset check-access <dataset_id> [<dataset_id> ...]
```
