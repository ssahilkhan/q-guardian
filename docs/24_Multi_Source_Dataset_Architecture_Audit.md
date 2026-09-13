# Multi-Source Dataset Architecture Audit & Design Proposal

> Generated: 2026-09-07
> Scope: Q-Guardian DatasetRegistry — audit of the dataset acquisition pipeline and a
> minimal, backward-compatible design proposal for supporting multiple dataset source types.
> Status: **architecture design complete — implementation requires review**.

---

## 1. Executive Summary

**Proven limitation:** The dataset pipeline is **HF-repository-centric**. The binding
assumption is concentrated in a single place — `DatasetDownloader`
(`src/q_guardian/benchmark/download.py`) — which routes **only** `format == "hf"` through
the huggingface datasets-server `/rows` API and treats every non-`hf` format as a local
file path. There is **no** code path for GitHub-hosted data, direct URL downloads,
archives, or any remote non-HF acquisition. In addition, **no revision/checksum pinning
exists anywhere** (the cache is keyed only by `dataset_id` + `split`), limiting
reproducibility.

**Is multi-source support necessary?** Yes. The registry audit proved 6 external-eval
datasets (`jailbreakbench-attacks`, `harmbench-behaviors`, `advbench`, `pal`,
`agentdojo`, `cyberseceval-prompt-injections`) have official sources that are not (or are
no longer) plain huggingface datasets-server-reachable repositories. Two are
architecturally mis-registered (`agentdojo` is an ETH Zürich GitHub project;
`jailbreakbench-attacks` artifacts live on GitHub), and the current downloader cannot
express them.

**Recommended minimal solution:** Add a **`source_type` field** to `DatasetSpec`
(default `"huggingface"`) plus **extend the existing `DatasetDownloader`** with a small
dispatch on that field (Option A data model + Option C downloader extension — see §5).
No new framework, no provider class hierarchy, no registry migration (the default value
is fully backward-compatible). Reproducibility additions are optional `revision` /
`checksum` fields defaulting to `None`.

---

## 2. Current Architecture

### 2.1 Diagram (verified against code)

```text
DatasetRegistry  (benchmark/registry.py)
    │  DatasetSpec (dataset_id, source, format, config, splits,
    │              text_fields, label_field, label_map, label_from_split,
    │              default_label, category_field, license, homepage,
    │              requires_token, max_samples)
    ▼
DatasetAuthResolver  (ml/datasets/auth.py) — OFFLINE classification only
    │  PUBLIC | GATED | AUTHENTICATED   (PRIVATE/UNAVAILABLE/INVALID declared,
    │                                    never produced)
    ▼
DatasetDownloader  (benchmark/download.py)
    │  GATED → raise DatasetError (no download attempted)
    │  format == "hf"       → datasets-server /rows  (paginated, JSONL cache)
    │  format ∈ jsonl,csv,json → Path(spec.source) local file
    ▼
JSONL cache  ~/.qguardian/benchmark/{dataset_id}__{split}.jsonl
    ▼
DatasetValidator (benchmark/validate.py) — offline, spec-driven, JSON-object/text/label
    │  + DatasetPreprocessor (benchmark/preprocessing.py) OR
    │    DatasetRecordPreprocessor (training/normalize.py)
    │    extract_text → resolve_label → extract_category   (ONE shared code path)
    ▼
PromptBenchmarkDataset / DatasetRecord
    ▼
BenchmarkRunner (benchmark/run.py)  ·  TrainingPrepPipeline (training/prepare.py)
```

### 2.2 Component responsibilities & HF assumptions

| Component | Responsibility | Current source assumptions | Limitations |
| --- | --- | --- | --- |
| `DatasetSpec` (`registry.py:19-71`) | Ingestion contract: schema + columns + provenance | `source` = "HF repo id or local file path"; `format ∈ {hf, jsonl, csv, json}` | No URL/GitHub; no revision/checksum; `format=="hf"` implies repo-id shape |
| `_gated_spec()` (`registry.py:78-105`) | Placeholder gated specs | Always `format="hf"`, `requires_token=True`, schema `None` | Schema "finalized later"; cannot represent non-HF gated/external |
| `DatasetRegistry` (`registry.py:208-246`) | Catalog by `dataset_id` | None beyond specs | None |
| `DatasetAuthResolver` (`ml/datasets/auth.py`) | Token resolution + access classification | `AuthProvider.HUGGINGFACE` only; offline (no network) | Cannot detect 404-vs-gated ambiguity; PRIVATE/UNAVAILABLE never emitted |
| `DatasetDownloader` (`benchmark/download.py`) | Acquisition → JSONL cache | `/rows` with `dataset=spec.source`; non-`hf` = local `Path` | **The key constraint**: only HF-server or local files |
| `DatasetValidator` (`benchmark/validate.py`) | Offline quality checks | None (pure spec + JSONL) | None |
| `DatasetPreprocessor` / `DatasetRecordPreprocessor` | Column → canonical mapping | None (spec-driven only) | None; fully provider-agnostic |
| CLI (`cli.py`) | `dataset prepare/validate/check-access/authenticate-status`, `benchmark`, `model train/evaluate` | Uses registry ids; `_resolve_token()` env → config | Token masking is secure; id → source via registry only |
| `HuggingFaceLoader` (`ml/datasets/huggingface_loader.py`) | Optional `datasets`-lib loading | HF-only, parallel, **no production consumer** (tests only) | Duplicate path; `DatasetEntry` schema differs from benchmark schema |
| `scripts/ml/external_study_manifest.py`, `dataset_manifest.py` | Docs/manifests | **Hard-coded duplicate** of spec fields (stale `walledai/HEx-PHI` at `external_study_manifest.py:201,208` confirmed) | Drift risk: hand-edited, not registry-driven |

### 2.3 Exact HF-specific points

1. `download.py:30` `ROWS_API` + `download.py:154` `dataset=spec.source` (repo-id required).
2. `download.py:116-119` non-`hf` formats route to `_load_local`, which requires an existing `Path`.
3. `auth.py:163` and `auth.py:261` branch on `spec.format != "hf"` → treat everything non-`hf` as "Local, no authentication required".
4. `auth.py:29-32` `AuthProvider` = huggingface only.

### 2.4 Lifecycle facts

- Training and benchmark **share** the same registry + downloader (`prepare.py:99`); both normalize through the **same** `extract_text` / `resolve_label` / `extract_category` helpers.
- Gated datasets are never downloaded: `download.py:105` raises before any request.
- No live `check_dataset_access` network verification — genuine access is only confirmed at download time (`auth.py:249-251` docstring).

---

## 3. Proven Limitations

| Source Type | Current Support | Limitation | Evidence |
| --- | --- | --- | --- |
| A. Public Hugging Face | **FULLY SUPPORTED** | None — works today | `deepset-prompt-injections`, `jbb-behaviors`, `dolly-benign` downloadable via `/rows` (verified) |
| B. Gated Hugging Face | **PARTIALLY SUPPORTED** | Classification works; **download blocked** (`DatasetError` on GATED); datasets-server may not index gated content; schema placeholder | `download.py:105-111`; `auth.py:154-203`; `_gated_spec` schema `None` |
| C. Private / authenticated | **NOT SUPPORTED** | `PRIVATE` / `UNAVAILABLE` / `INVALID` exist in enum + CLI labels but are **never produced** by the resolver; no provider network probe | `auth.py:18-26` vs calls at 166/175/187/200 — only PUBLIC/AUTHENTICATED/GATED constructed |
| D. GitHub-hosted | **NOT SUPPORTED** | No `source_type`; a GitHub repo id would be passed to `/rows` and 404, or misjudged as a local path | AgentDojo (ethz-spylab) & JBB artifacts registered as HF ids; `download.py:154,197` |
| E. Direct file / URL downloads | **NOT SUPPORTED** | Local formats require an existing `Path`; **no URL fetch, no zip/tar/parquet unpacking** in `src` | `download.py:196-202`; no `urlopen`/`parquet`/`zip` in the download layer |
| F. External research repos | **NOT SUPPORTED** | Only representable via the `homepage` string (provenance link); no acquisition path | PAL, CyberSecEval registered as non-existent HF ids (prior audit, 404s) |

---

## 4. Recommended Architecture

### 4.1 Minimal changes

Extend `DatasetSpec` with **defaulted, backward-compatible fields** (`registry.py`):

| New field | Default | Why needed / limitation solved | Compatibility |
| --- | --- | --- | --- |
| `source_type: str = "huggingface"` | `"huggingface"` | Routable acquisition; solves D/F (GitHub, external) | Existing specs unchanged |
| `revision: str \| None = None` | `None` | Pin GitHub commits / HF revisions; solves reproducibility | No-op when `None` |
| `checksum: str \| None = None` | `None` | File/bundle integrity after download; solves security + data-integrity | No-op when `None` |

Allowed `source_type` values: `"huggingface" | "github" | "direct_url" | "external"`.
**`format` retains its meaning**: serialization shape of the *acquired* data (`hf`,
`jsonl`, `csv`, `json`) — orthogonal to *where* it comes from.

### 4.2 Downloader dispatch (the only code change needed)

In `DatasetDownloader`:

```text
download(spec):
    if format in (jsonl,csv,json) and not a remote source_type → local path  (existing _load_local)
    else dispatch on spec.source_type:
        "huggingface" → _download_hf            (existing /rows path, unchanged)
        "github"      → _download_github        (~40 lines: raw-file GET or tarball)
        "direct_url"  → _download_url           (file GET, optional checksum verify)
        "external"    → raise DatasetError      ("external source, no auto-download")
        else          → raise DatasetError      (unsupported source type)
```

All strategies write rows into the **same JSONL contract** `{dataset_id}__{split}.jsonl`, so
the validator and normalizer are untouched.

### 4.3 Auth interaction (no change to auth.py logic)

- `huggingface` → existing `DatasetAuthResolver` (HF token flow, unchanged).
- `huggingface` gated → existing GATED classification + terms acceptance at `homepage`.
- `"github"` / `"direct_url"` public → **no auth**; the resolver's `classify_access` returns PUBLIC for these (see §8).
- `"external"` → no auth layer; treated as "not auto-downloadable" (must be provisioned manually), matching current PAL / CyberSecEval reality.
- Keep `AuthProvider.HUGGINGFACE`; **add no GitHub/private secret handling** (out of scope).

### 4.4 Registry compatibility

- `source_type` default = `"huggingface"` → every one of the 11 existing specs behaves
  identically with zero edits.
- `revision` / `checksum` default `None` → no serialization break (`to_dict` includes them
  only as `"revision": null`).
- `scripts/ml/dataset_manifest.py` reads `spec.source` (fine); `external_study_manifest.py`
  remains a hard-coded doc (drift already present — flagged, not fixed in this audit).

---

## 5. Alternatives Considered

| Option | Complexity | Backward compat | Testability | Security | Extensibility | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| **A. Strategy field** (`source_type` on spec) | Low — 1 field + dispatch | Perfect via default | High — pure routing | Neutral | High (new types = new case) | Low |
| **B. Provider class hierarchy** (`DatasetSourceProvider` base + HF/GitHub/Direct subclasses) | High — new ABC + 3 classes + registry-of-providers | Requires adapter for existing downloader | Higher seam but more surface | Neutral | High but unnecessary now | **Rejected**: theoretical elegance, not warranted by 8 remote entries |
| **C. Extend existing `DatasetDownloader`** (dispatch inside one class on `format` + `source_type`) | Low-Medium — one method + 2 small fetchers | Perfect — existing `/rows` + `_load_local` preserved untouched | High — inject `httpx` transport already exists (test seam at `download.py:61`) | Neutral (only adds well-scoped endpoints) | Adequate | **Recommended** |

**Recommendation: A + C.** Add `source_type` to the spec (data model, A) and implement
dispatch inside the existing downloader (C). The codebase already has
`transport: httpx.BaseTransport` injection and `DatasetError` — both are the natural
extension points. This is the smallest design that fits the actual repo; provider classes
(B) add an inheritance hierarchy the codebase does not need.

---

## 6. Dataset Migration Plan

| Phase | Scope | Datasets | Action |
| --- | --- | --- | --- |
| **A** | Preserve | `deepset-prompt-injections`, `jbb-behaviors`, `dolly-benign` (public HF) | **No change** — already working |
| **B** | Add abstraction | — | Add `source_type` (+ `revision`/`checksum`) with defaults; zero registry migration |
| **C** | **Proof of concept** | **`advbench` via official GitHub `llm-attacks/llm-attacks` `data/advbench/harmful_behaviors.csv`** | Safest PoC: official source, public, **single CSV**, no auth, high benchmark importance, trivial schema (`goal` text → default malicious label). (JBB artifacts = multi-file TSV; AgentDojo = task-suite structure; both more complex — defer.) |
| **D** | Validate | PoC | Unit + integration tests; mirror-check against expected row count/columns |
| **E** | Individual migration | `jailbreakbench-attacks` → `JailbreakBench/artifacts` GitHub; `harmbench-behaviors` → `centerforaisafety/HarmBench` GitHub CSV; `agentdojo` → `ethz-spylab/agentdojo` GitHub | One per review cycle |
| **Requires source verification** | Do **not** migrate yet | `pal`, `cyberseceval-prompt-injections` | Provenance still unresolved (prior audit) — stay placeholders; `hex-phi` (already corrected to `LLM-Tuning-Safety/HEx-PHI`) and `wildjailbreak` remain HF-gated |

No bulk migration; each external dataset lands only after its source is independently
verified.

---

## 7. Risk and Security Analysis

| Risk | Example | Mitigation |
| --- | --- | --- |
| Wrong/unofficial mirrors (data integrity) | `walledai/*` community mirrors for AdvBench/HarmBench | PoC uses **official GitHub orgs only** (`llm-attacks`, `centerforaisafety`, `JailbreakBench`, `ethz-spylab`); never auto-substitute on similar names (enforced since the registry audit) |
| Changed upstream content (reproducibility) | GitHub file edited after pinning | `revision` (commit/tag) + `checksum` fields; document resolved revision in manifest |
| Mutable URLs / dead endpoints | Direct URL CSV rotated by provider | Pin revision + verify checksum; fail loudly on mismatch; `DatasetError` on 404 with hint |
| Untrusted downloads / redirects / malicious archives | Remote fetch of attacker-controlled file | Whitelist allowed `source_type`; no archive unpacking in PoC (CSV/JSONL only); checksum verification; existing `httpx` security defaults |
| Secret leakage | Token in URL/log/exception | `DatasetAuthResolver` never logs token (`download.py:77-83`); headers-only auth via `get_auth_headers`; `training/config.py:187` masks `hf_token`; new GitHub/direct paths send **no** headers for public sources |
| Substituting non-equivalent datasets (benchmark validity) | Replacing `cyberseceval-prompt-injections` text data with the visual-prompt-injection dataset | Provenance rule: classify each candidate `EXACT OFFICIAL / OFFICIAL MOVED / VERIFIED MIRROR / POSSIBLE / NO REPLACEMENT` before any change (registry audit artifacts) |
| Silent schema changes | CSV column rename upstream | Validation is already spec-driven; validator reports schema drift (`validate.py:85-93`); keep schemas explicit per spec |
| Breaking public HF workflows / CLI | New field breaks `to_dict` | Field defaults preserve behavior; full registry test suite re-run in Phase B |
| Duplicated metadata drift | `external_study_manifest.py` still says `walledai/HEx-PHI` | Flagged in this audit (§2.2); future phase: generate manifest from the registry instead of hand-editing |

---

## 8. Testing Plan

**Unit tests**

- `source_type` validation (allowed/denied values, default `"huggingface"`).
- Routing: each `source_type` dispatches to the correct strategy; unknown type → `DatasetError`.
- Unsupported source errors: `"external"` → no auto-download; `format` mismatch → clear error.
- Backward compatibility: existing HF specs serialize identically and download via the unchanged `/rows` path.
- `revision` / `checksum` field presence/serialization (`to_dict` includes them, `None` by default).

**Downloader tests (with `httpx.MockTransport`)**

- Public HF source → `/rows` pagination happy path (existing tests extended).
- Gated HF source → mocks: classified `GATED` → `DatasetError`, plus 401/403/404 hint paths.
- External public source (`github` / `direct_url`) → raw-file fetch → JSONL cache contract.
- Invalid source (unknown `source_type`, missing URL, nonexistent raw path).

**Security tests**

- Authentication token **never** leaked in messages/exceptions (existing `test_dataset_auth.py` no-overclaim test retained).
- Credentials never stored in source metadata / `to_dict`.
- Public-source paths send no `Authorization` header.

**Integration tests**

- Existing public datasets still run end-to-end (registry → download → validate → preprocess).
- PoC `advbench` from the official GitHub CSV produces expected row count/columns.
- Normalization layer unchanged (`extract_text` / `resolve_label` / `extract_category` received identical inputs from the new strategy).

Test implementations are deferred to the implementation phases — not added during this audit.

---

## 9. Proposed Implementation Phases

| Phase | Objective | Files/components likely affected | Risk | Validation |
| --- | --- | --- | --- | --- |
| 1 | Add `source_type` (+ `revision` / `checksum`) fields with defaults | `benchmark/registry.py`, tests | Low | Registry suite green; `to_dict` stable |
| 2 | Add downloader dispatch + `github` / `direct_url` / `external` strategies | `benchmark/download.py`, tests | Low-Med | Mocked-transport downloader tests green |
| 3 | PoC: `advbench` from official GitHub CSV with explicit schema + pin | `registry.py`, `config.py` notes, tests | Med | Integration test: exact row count, columns, labels |
| 4 | Update auth classification for non-HF source types | `ml/datasets/auth.py`, tests | Low | `classify_access` returns PUBLIC for public github/direct; GATED unchanged |
| 5 | Document + manifest de-duplication | `scripts/ml/*`, docs | Low | Manifest regenerated from registry; stale HEx-PHI duplication removed |
| 6 | Individual migration of verified external datasets (per prior classification) | registry + tests | Med | One dataset per review, provenance documented |

---

## 10. Recommendation

The investigation produced a **clear, low-risk, backward-compatible design** (defaulted
`source_type` field + extended existing downloader; optional `revision` / `checksum` for
reproducibility) with a precisely recommended proof-of-concept (`advbench` via the
official GitHub CSV). However, two datasets (`pal`, `cyberseceval-prompt-injections`)
still have unresolved provenance, the stale manifest duplication requires a separate
cleanup decision, and the field-naming/scope choices warrant human sign-off before
implementation begins.

**ARCHITECTURE DESIGN COMPLETE — IMPLEMENTATION REQUIRES REVIEW**