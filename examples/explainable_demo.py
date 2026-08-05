"""Explainable Demo Mode for Q-Guardian.

Visualizes the complete runtime execution pipeline of Q-Guardian for live
thesis / research demonstrations. This is NOT a simulation and it does NOT
re-implement anything: the script reuses the existing Q-Guardian pipeline
(``examples/prompt_test_harness.py``) and adds an explainability layer that
captures and renders every intermediate computation produced by the real code.

The ten steps rendered:

    1.  User input            - raw prompt statistics
    2.  Preprocessing         - PromptNormalizer + PromptValidator, stage by stage
    3.  Feature extraction    - every extracted feature + the full 43-dim vector
    4.  Rule engine           - every rule checked, every match explained
    5.  Classical ML          - RandomForest + IsolationForest internals
    6.  Quantum pipeline      - encoding, feature map, circuit, kernel, QSVM
    7.  Hybrid fusion         - weighted soft voting across all providers
    8.  Final output          - safe %, threat %, risk, verdict, action
    9.  Code trace            - file -> class -> method -> execution order
    10. Feature explanation   - one entry per feature (--explain-features)

Usage:
    python examples/explainable_demo.py
    python examples/explainable_demo.py "your prompt here"
    python examples/explainable_demo.py "prompt A" "prompt B"
    python examples/explainable_demo.py --explain-features "prompt"
    python examples/explainable_demo.py --export-mermaid demo.mmd "prompt"
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import re
import sys
import time
import unicodedata
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import numpy as np
import structlog

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "examples" / "prompt_test_harness.py"

_SPEC = importlib.util.spec_from_file_location("prompt_test_harness", HARNESS)
assert _SPEC is not None and _SPEC.loader is not None, "harness import failed"
HARNESS_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(HARNESS_MOD)
Pipeline = HARNESS_MOD.Pipeline

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(50),
    processors=[structlog.processors.add_log_level],
    logger_factory=structlog.PrintLoggerFactory(),
)

QUANTUM_FEATURE_COUNT = HARNESS_MOD.QUANTUM_FEATURE_COUNT
QUANTUM_SHOTS = HARNESS_MOD.QUANTUM_SHOTS


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------


def _header(title: str, width: int = 72) -> None:
    print()
    print("=" * width)
    print(title)
    print("=" * width)


def _sub(title: str) -> None:
    print()
    print("-" * 66)
    print(f"  {title}")
    print("-" * 66)


def _kv(label: str, value: Any, indent: int = 2) -> None:
    print(f"{' ' * indent}{label:<26}{value}")


def _truncate(text: str, limit: int = 64) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _escape(text: str) -> str:
    return text.encode("unicode_escape").decode("ascii")


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _bar(value: float, width: int = 32) -> str:
    filled = max(0, min(width, round(value * width)))
    return "#" * filled + "." * (width - filled)


def _arrow(text: str) -> str:
    return f"  ->  {text}"


def _rel(file: str) -> str:
    try:
        return str(Path(file).resolve().relative_to(ROOT))
    except ValueError:
        return str(file)


# ---------------------------------------------------------------------------
# Feature catalog (auto-discovered + educational metadata)
# ---------------------------------------------------------------------------


STAT_DEFS: dict[str, dict[str, str]] = {
    "length": {
        "definition": "Total number of characters in the normalized prompt.",
        "formula": "len(prompt)",
        "why": "Very long prompts can hide an injection behind filler text or "
        "trigger the OVERSIZED_PROMPT rule family.",
    },
    "word_count": {
        "definition": "Number of whitespace-separated words.",
        "formula": "len(prompt.split())",
        "why": "A proxy for prompt complexity; long prompts carry more attack surface.",
    },
    "line_count": {
        "definition": "Number of newline-delimited lines.",
        "formula": "len(prompt.split('\\n'))",
        "why": "Unusual line structure is a signal of crafted multi-line payloads.",
    },
    "token_estimate": {
        "definition": "Estimated token count using the ~4 chars/token approximation.",
        "formula": "max(1, len(prompt) // 4)",
        "why": "Estimates the context budget a prompt would consume at inference.",
    },
    "entropy": {
        "definition": "Shannon entropy of the character distribution.",
        "formula": "-sum(p(x) * log2(p(x))) over all characters x",
        "why": "High entropy text is atypical for natural language and can signal "
        "encoded/obfuscated payloads.",
    },
    "uppercase_ratio": {
        "definition": "Fraction of alphabetic characters that are uppercase.",
        "formula": "uppercase_characters / alphabetic_characters",
        "why": "Shouting / emphasis patterns appear in coercion-style attacks.",
    },
    "digit_ratio": {
        "definition": "Fraction of all characters that are digits.",
        "formula": "digit_characters / len(prompt)",
        "why": "High digit density is common in keys, tokens, and encoded payloads.",
    },
    "special_char_count": {
        "definition": "Count of characters that are neither alphanumeric nor whitespace.",
        "formula": "count of c where not c.isalnum() and not c.isspace()",
        "why": "Punctuation and symbol density rises in obfuscated or technical payloads.",
    },
    "suspicious_keyword_count": {
        "definition": "Number of known prompt-injection / jailbreak keyword phrases found.",
        "formula": "len(features.suspicious_keywords)",
        "why": "Direct evidence of injection vocabulary such as 'ignore previous'.",
    },
}

PATTERN_DEFS: dict[str, dict[str, str]] = {
    "code_block_count": {
        "definition": "Number of fenced ``` code blocks (count of '```' divided by 2).",
        "formula": "prompt.count('```') // 2",
        "why": "Code blocks are the preferred container for injected instructions.",
    },
    "url_count": {
        "definition": "Number of http(s) URLs found.",
        "formula": "len(re.findall(r'https?://\\S+', prompt))",
        "why": "URLs can point at attacker-controlled endpoints or mark data-exfil attempts.",
    },
    "markdown_usage": {
        "definition": "1 if markdown syntax (headers, bold, lists, code) is present, else 0.",
        "formula": "any(re.search(pattern, prompt) for pattern in MARKDOWN_PATTERNS)",
        "why": "Structured markdown is a common formatting trick in injected content.",
    },
    "has_unicode_escaped": {
        "definition": "1 if a \\uXXXX unicode escape sequence is present, else 0.",
        "formula": "bool(re.search(r'\\\\u[0-9a-fA-F]{4}', prompt))",
        "why": "Unicode escapes are used to bypass keyword detection.",
    },
    "has_html_tags": {
        "definition": "1 if an HTML/XML tag like <...> is present, else 0.",
        "formula": "bool(re.search(r'<[^>]+>', prompt))",
        "why": "HTML/XML tags can smuggle payloads or enable SSRF-style wording.",
    },
    "repeated_pattern_count": {
        "definition": "Number of distinct words repeated 3 or more times.",
        "formula": "len([w for w in counts if counts[w] >= 3])",
        "why": "Repetition is a naive attention/guardrail-spam technique.",
    },
}

CHAR_DEFS: dict[str, dict[str, str]] = {
    "unique_char_ratio": {
        "definition": "Unique characters divided by total characters (character diversity).",
        "formula": "len(set(prompt)) / len(prompt)",
        "why": "Extreme diversity hints at obfuscation; near-zero diversity hints at spam.",
    },
    "avg_word_length": {
        "definition": "Mean length of whitespace-separated words.",
        "formula": "sum(len(w) for w in words) / max(len(words), 1)",
        "why": "Unusually long words are typical of keys, hashes, and token leaks.",
    },
    "punctuation_ratio": {
        "definition": "Non-alphanumeric, non-whitespace characters divided by total characters.",
        "formula": "punctuation_characters / len(prompt)",
        "why": "Heavy punctuation appears in crafted formatting and injection payloads.",
    },
    "whitespace_ratio": {
        "definition": "Whitespace characters divided by total characters.",
        "formula": "whitespace_characters / len(prompt)",
        "why": "Irregular whitespace can hide payloads from visual review.",
    },
}


def _category_of(name: str) -> str:
    if name in STAT_DEFS:
        return "Statistical"
    if name in PATTERN_DEFS:
        return "Pattern"
    if name in CHAR_DEFS:
        return "Character distribution"
    if name.startswith("kw_"):
        return "Keyword flag"
    return "Other"


def _function_of(name: str) -> str:
    if name in CHAR_DEFS:
        return "MLFeatureProvider._char_distribution()"
    if name in PATTERN_DEFS or name in STAT_DEFS:
        return "PromptFeatureExtractor.extract()"
    if name.startswith("kw_"):
        return "MLFeatureProvider._keyword_flags()"
    return "MLFeatureProvider.extract_vector()"


def _file_of(name: str) -> str:
    if name in CHAR_DEFS or name.startswith("kw_"):
        return "src/q_guardian/ml/feature_pipeline.py"
    return "src/q_guardian/security/pipeline.py"


def _variable_of(name: str) -> str:
    if name.startswith("kw_"):
        return f'features["{name}"]'
    return f'features["{name}"]'


def feature_meta(name: str) -> dict[str, str]:
    if name.startswith("kw_"):
        keyword = name[3:]
        return {
            "definition": (
                f"Occurrence count of the suspicious keyword '{keyword}' in the lower-cased prompt."
            ),
            "formula": f"prompt.lower().count('{keyword}')",
            "why": f"Direct keyword evidence — '{keyword}' is in the ML suspicious "
            "keyword vocabulary.",
        }
    source = STAT_DEFS.get(name) or PATTERN_DEFS.get(name) or CHAR_DEFS.get(name)
    if source is None:
        return {
            "definition": "Feature extracted by the ML feature pipeline.",
            "formula": "see MLFeatureProvider",
            "why": "Contributes to the numeric vector consumed by the models.",
        }
    return source


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------


class ExplainableRunner:
    """Reuses the existing Q-Guardian Pipeline and instruments every stage."""

    def __init__(self) -> None:
        t0 = time.monotonic()
        print("Initializing Q-Guardian explainable demo ...")
        with redirect_stdout(io.StringIO()):
            self.pipeline = Pipeline(skip_train=False)
        self._init_ms = (time.monotonic() - t0) * 1000
        print(f"  Pipeline ready in {self._init_ms:.1f} ms")
        print(
            f"  Classical ML : RandomForest({self.pipeline.rf._n_estimators} trees), "
            f"IsolationForest(contamination={self.pipeline.anomaly._contamination})"
        )
        print(
            f"  Quantum      : QSVM, AngleEncodingMap({QUANTUM_FEATURE_COUNT} qubits), "
            f"LocalSimulatorBackend(shots={QUANTUM_SHOTS})"
        )
        print(
            f"  Fusion       : {self.pipeline.fusion.active_strategy_name} with "
            f"{self.pipeline.fusion.provider_count} providers"
        )
        print(
            f"  Corpus       : {len(self.pipeline._train_texts)} training samples "
            f"({sum(1 for _, y in self.pipeline._train_texts if y == 0)} benign / "
            f"{sum(1 for _, y in self.pipeline._train_texts if y == 1)} malicious)"
        )

    # -- STEP 1 ------------------------------------------------------------
    def _render_step1(self, prompt: str) -> None:
        _header("STEP 1 - USER INPUT")
        _kv("Prompt", repr(prompt))
        _kv("Characters", len(prompt))
        _kv("Words", len(prompt.split()))
        _kv("Tokens", max(1, len(prompt) // 4) if prompt else 0)
        _kv(
            "Language",
            self._detect_script(prompt) + "  (display-only heuristic, not a Q-Guardian feature)",
        )
        _kv(
            "Hidden characters",
            len(
                [
                    c
                    for c in prompt
                    if unicodedata.category(c) in ("Cf", "Cc") and c not in ("\n", "\t")
                ]
            ),
        )

    @staticmethod
    def _detect_script(text: str) -> str:
        for ch in text:
            if not ch.isalpha():
                continue
            if ord(ch) > 0x2FFF:
                name = unicodedata.name(ch, "")
                if "CJK" in name or 0x4E00 <= ord(ch) <= 0x9FFF:
                    return "Likely CJK (non-ASCII present)"
                if "GREEK" in name:
                    return "Likely Greek (non-ASCII present)"
                if "CYRILLIC" in name:
                    return "Likely Cyrillic (non-ASCII present)"
                if "ARABIC" in name:
                    return "Likely Arabic (non-ASCII present)"
                return "Non-ASCII script present"
        return "English (ASCII)"

    # -- STEP 2 ------------------------------------------------------------
    def _trace_normalization(self, prompt: str) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []

        def record(name: str, purpose: str, before: str, after: str, detail: str = "") -> None:
            steps.append(
                {
                    "name": name,
                    "purpose": purpose,
                    "before": before,
                    "after": after,
                    "changed": before != after,
                    "detail": detail,
                }
            )

        text = prompt
        before = text
        text = unicodedata.normalize("NFKC", text)
        record(
            "Unicode Normalization (NFKC)",
            "Compatibility decomposition + canonical composition so that lookalike "
            "characters cannot bypass detectors.",
            before,
            text,
        )

        before = text
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        record(
            "Line Endings Normalization",
            "Converts CRLF and CR line endings to a single LF representation.",
            before,
            text,
        )

        before = text
        removed = 0
        kept: list[str] = []
        for char in text:
            if char in ("\n", "\t"):
                kept.append(char)
                continue
            if unicodedata.category(char) in ("Cf", "Cc"):
                removed += 1
                continue
            kept.append(char)
        text = "".join(kept)
        record(
            "Hidden Character Detection",
            "Removes invisible/control characters (Unicode categories Cf and Cc), "
            "keeping newlines and tabs for structure.",
            before,
            text,
            f"found={removed} removed={removed}",
        )

        before = text
        text = text.strip()
        record(
            "Trimming",
            "Removes leading and trailing whitespace.",
            before,
            text,
        )

        before = text
        text = re.sub(r"[^\S\n]+", " ", text)
        record(
            "Whitespace Collapse",
            "Collapses multiple spaces to a single space while preserving newlines.",
            before,
            text,
        )

        before = text
        text = re.sub(r"\n{3,}", "\n\n", text)
        record(
            "Blank Line Collapse",
            "Collapses runs of 3+ newlines down to two.",
            before,
            text,
        )
        return steps

    def _render_step2(self, prompt: str, normalized: str) -> None:
        _header("STEP 2 - PREPROCESSING")
        print("  Module  : PromptNormalizer  (src/q_guardian/security/pipeline.py)")
        print(
            "  Purpose : normalize text before feature extraction so detectors "
            "cannot be bypassed with encoding tricks"
        )
        steps = self._trace_normalization(prompt)

        for i, step in enumerate(steps, start=1):
            _sub(f"{i}. {step['name']}")
            _kv("Purpose", step["purpose"])
            _kv("Before", _truncate(repr(step["before"]), 72))
            _kv("After ", _truncate(repr(step["after"]), 72))
            if step["detail"]:
                _kv("Detail", step["detail"])
            _kv("Changed", "yes" if step["changed"] else "no")

        _sub("Additional normalizer notes")
        _kv(
            "Lowercase conversion",
            "NOT APPLIED - Q-Guardian preserves case on purpose; case information "
            "survives as the uppercase_ratio feature.",
        )
        _kv(
            "Special character handling",
            "NOT STRIPPED - special characters are counted, not removed, so "
            "evidence survives as special_char_count.",
        )

        _sub("Validation  (PromptValidator)")
        status, errors = self.pipeline.validator.validate(normalized)
        _kv("Status", status.value)
        _kv("Errors", errors if errors else "none")

        _sub("Transformed prompt after all preprocessing stages")
        print(f"  {normalized!r}")

    # -- STEP 3 ------------------------------------------------------------
    def _render_step3(self, trace: dict[str, Any]) -> None:
        names: list[str] = trace["feature_names"]
        raw: list[float] = trace["raw_vector"]
        scaled: list[float] = trace["scaled_vector"]
        base = trace["base_features"]

        _header("STEP 3 - FEATURE EXTRACTION")
        print("  Two layers extract features from the normalized prompt:")
        print("    (a) PromptFeatureExtractor.extract()   -> PromptFeatures model")
        print("    (b) MLFeatureProvider.extract_vector() -> 43-dim numeric vector")

        _sub("(a) Base features - PromptFeatures")
        for name in [
            "length",
            "word_count",
            "line_count",
            "token_estimate",
            "special_char_count",
            "code_block_count",
            "url_count",
            "markdown_usage",
            "entropy",
            "uppercase_ratio",
            "digit_ratio",
            "has_unicode_escaped",
            "has_html_tags",
        ]:
            value = getattr(base, name)
            desc = (STAT_DEFS.get(name) or PATTERN_DEFS.get(name))["definition"]
            print(f"    {name:<24} = {value!s:<12} | {_truncate(desc, 42)}")
        print(f"    {'suspicious_keywords':<24} = {base.suspicious_keywords}")
        print(f"    {'repeated_patterns':<24} = {base.repeated_patterns}")
        print(
            "    computed by PromptFeatureExtractor.extract() "
            "in src/q_guardian/security/pipeline.py"
        )

        _sub("(b) Complete 43-dimensional ML feature vector (RAW)")
        groups = self._group_features(names, raw)
        for group, items in groups:
            fn = _function_of(items[0][0])
            src = _file_of(items[0][0])
            print(f"    -- {group}  (computed by {fn} in {src}) --")
            for name, value in items:
                meta = feature_meta(name)
                print(f"      {name:<26}= {value:g}")
                print(f"          {_truncate(meta['definition'], 78)}")
            print()

        _sub("Complete raw feature vector")
        print(f"  {[round(v, 4) for v in raw]}")

        _sub("Standardized vector - EXACTLY what the models receive")
        print("  StandardScaler was fitted on the 20-sample training corpus and")
        print("  transforms each feature to zero mean / unit variance:")
        print(f"  scaled = {[round(v, 4) for v in scaled]}")
        _kv("Consumed by", "RandomForestThreatClassifier.predict() (all 43 values)")
        _kv("", "IsolationForestDetector.predict() (all 43 values)")
        _kv("", f"QSVMModel.predict() (first {QUANTUM_FEATURE_COUNT} values only)")
        _kv(
            "Why this vector exists",
            "classical ML and the quantum kernel need fixed-length numeric input; "
            "scaling prevents large-count features from dominating the models",
        )

    @staticmethod
    def _group_features(
        names: list[str], values: list[float]
    ) -> list[tuple[str, list[tuple[str, float]]]]:
        groups: dict[str, list[tuple[str, float]]] = {}
        for name, value in zip(names, values, strict=False):
            groups.setdefault(_category_of(name), []).append((name, value))
        order = ["Statistical", "Keyword flag", "Pattern", "Character distribution"]
        return [(g, groups[g]) for g in order if g in groups]

    # -- STEP 4 ------------------------------------------------------------
    def _render_step4(self, trace: dict[str, Any]) -> None:
        _header("STEP 4 - RULE ENGINE")
        print("  Module : RuleEngine  (src/q_guardian/security/pipeline.py)")
        rules = trace["rules_checked"]
        findings = trace["findings"]
        print(f"  Rules checked: {rules}")
        for rule in self.pipeline.rule_engine.list_rules(enabled_only=True):
            matched = next((f for f in findings if f.rule_id == rule.rule_id), None)
            status = "MATCHED" if matched else "not matched"
            marker = "[*]" if matched else "[ ]"
            print(
                f"    {marker} {rule.rule_id:<8} {rule.name:<34} {status}"
                + (
                    f"  (severity={matched.severity.value}, confidence={matched.confidence})"
                    if matched
                    else ""
                )
            )

        _sub("Why the matched rules fired")
        if not findings:
            print(
                "  No rules fired: none of the rule keywords or regex patterns "
                "appeared in the normalized prompt."
            )
            print(
                "  The prompt does not use injection vocabulary, role-switching "
                "phrases, or encoded-formatting patterns."
            )
        for f in findings:
            _kv(f"{f.rule_id} - {f.rule_name}", f"category={f.category.value}")
            _kv("matched text", repr(f.matched_text))
            _kv("severity", f.severity.value)
            _kv("confidence", f.confidence)

    # -- STEP 5 ------------------------------------------------------------
    def _render_step5(self, trace: dict[str, Any]) -> None:
        _header("STEP 5 - CLASSICAL ML")
        scaled = trace["scaled_vector"]
        rf = trace["rf"]
        rf_votes = trace["rf_votes"]
        anomaly = trace["anomaly"]

        _sub("Random Forest - RandomForestThreatClassifier")
        print("  file     : src/q_guardian/ml/models/classifier.py")
        print("  ensemble : 50 decision trees (n_estimators), trained on the 20-sample corpus")
        print("  input    : 43-dim standardized feature vector")
        print(f"    {[round(v, 4) for v in scaled[:10]]} ... ({len(scaled)} values)")
        _kv("Prediction", rf["predicted_class"])
        probs = rf["probabilities"]
        for label, prob in probs.items():
            _kv(f"P({label})", f"{prob:.4f}  {_bar(prob)}")
        _kv("Confidence", f"{rf['confidence']:.4f} (top-class probability)")
        print("  tree votes:")
        for label, count in sorted(rf_votes.items()):
            share = count / max(sum(rf_votes.values()), 1)
            print(
                f"    {label:<18} {count:>3} / {sum(rf_votes.values())} trees "
                f"({_bar(share)}) {_pct(share)}"
            )
        _kv(
            "How it works",
            "each tree splits on the 43 features and votes; predict_proba averages "
            "leaf probabilities across all 50 trees",
        )

        _sub("Isolation Forest - IsolationForestDetector")
        print("  file     : src/q_guardian/ml/models/anomaly.py")
        print(
            "  idea     : anomalies are easy to isolate, so they sit on shorter "
            "average paths in the random split forest"
        )
        print("  input    : 43-dim standardized feature vector")
        raw_score = float(anomaly.get("raw_score", 0.0))
        anom_score = float(anomaly.get("anomaly_score", 0.0))
        _kv("Raw decision_function", f"{raw_score:.4f}   (lower = more anomalous)")
        _kv("Mapped anomaly score", f"{anom_score:.4f}   = clamp(0.5 - raw_score, 0, 1)")
        _kv("is_anomaly", anomaly["is_anomaly"])
        _kv("Threshold", "decision_function < 0  ->  isolated as -1")
        _kv("Contamination", self.pipeline.anomaly._contamination)

    # -- STEP 6 ------------------------------------------------------------
    def _render_step6(self, trace: dict[str, Any]) -> None:
        _header("STEP 6 - QUANTUM PIPELINE")
        q_vec = trace["q_vector"]
        enc = trace["q_encoding"]
        circuit_info = trace["q_circuit_info"]
        sims = trace["q_kernel_sims"]
        qr = trace["q"]

        print("  Module : QSVMModel  (src/q_guardian/quantum/models/qsvm.py)")
        print(
            "  chain  : feature vector -> encoding -> feature map -> circuit "
            "-> kernel -> QSVM -> prediction"
        )
        print()
        print("  feature vector (first 5 standardized values)")
        print(f"    {[round(v, 4) for v in q_vec]}")
        print(_arrow("AngleEncodingMap.encode()"))
        print(
            f"  feature map : {enc.metadata.get('feature_map')}  "
            f"(name={self.pipeline._q_feature_map.name})"
        )
        print(
            f"  qubits      : {enc.num_qubits}  "
            f"(rotation gates: {self.pipeline._q_feature_map.rotation_gates})"
        )

        _sub("Encoded circuit (angle encoding -> Ry rotations)")
        gates = enc.circuit["gates"]
        for gate in gates:
            q = ",".join(str(x) for x in gate["qubits"])
            params = ",".join(f"{p:.3f}" for p in gate.get("params", []))
            print(f"    qubit[{q}]  {gate['type']}({params})")
        if self.pipeline._q_feature_map.name == "angle-encoding":
            self._print_angle_diagram(q_vec, enc.num_qubits)

        _sub("Kernel - QuantumKernelEstimator (SWAP test)")
        print("  kernel        : " + self.pipeline._q_kernel.name)
        print("  backend       : " + self.pipeline._q_kernel.backend.name)
        print(f"  shots         : {QUANTUM_SHOTS}")
        print(
            f"  circuit       : {circuit_info.num_qubits} qubits, "
            f"depth={circuit_info.depth}, gates={circuit_info.gate_count}"
        )
        print("  formula       : K(x1, x2) = |<phi(x1)|phi(x2)>|^2  (state overlap fidelity)")
        self._print_swap_test_diagram(enc.num_qubits)

        _sub(f"Kernel similarities vs {len(sims)} support vectors")
        sim_values = [k for _, k in sims]
        for i, (label, k) in enumerate(sims):
            print(f"    sv#{i:<3} y={label}  K={k:.4f} {_bar(k)}")
        print(
            f"    min={min(sim_values):.4f}  mean={sum(sim_values) / len(sim_values):.4f}"
            f"  max={max(sim_values):.4f}"
        )
        print("  (these are the exact kernel.evaluate() calls QSVMModel.predict() makes)")

        _sub("QSVM decision")
        svm = self.pipeline.qsvm
        print("  support vectors : " + str(len(svm.support_vectors)))
        print(
            "  dual coeffs     : alpha_j = " + str(sorted({round(a, 4) for a in svm._dual_coeffs}))
        )
        print("  bias            : " + f"{svm.bias:.4f}")
        print(
            "  decision formula: score_c = sum_j [ s_j * alpha_j * K(x, sv_j) ] "
            "+ bias,  s_j = +1 if y_j == c else -1"
        )
        for cls, score in qr["scores"].items():
            print(f"    class {cls}: score = {score:.4f}")
        for cls, prob in qr["probabilities"].items():
            print(f"    class {cls}: probability = {prob:.4f}")
        _kv("Prediction", f"class {qr['predicted_class']}  (confidence {qr['confidence']:.4f})")
        _kv(
            "What the QSVM is doing",
            "encodes the 5-feature vector into a quantum state, measures its "
            "overlap (kernel) against every support vector, then applies the "
            "learned dual coefficients + bias to pick the winning class",
        )

    def _print_angle_diagram(self, q_vec: list[float], n: int) -> None:
        print()
        for i in range(n):
            angle = q_vec[i]
            print(f"    q{i} ---Ry({angle:.3f})---|M")
        print()

    @staticmethod
    def _print_swap_test_diagram(n: int) -> None:
        print("    kernel circuit: 2n+1 qubits, one SWAP test per pair")
        print("    q0   ---H--.*.....*---H--- measure  (ancilla)")
        print(f"    q1..q{n}    |  reg A (encoded x1)")
        print(f"    q{n + 1}..q{2 * n}   |  reg B (encoded x2)")
        print("    controlled-SWAP between A and B measures their overlap")
        print()

    # -- STEP 7 ------------------------------------------------------------
    def _render_step7(self, trace: dict[str, Any]) -> None:
        _header("STEP 7 - HYBRID FUSION")
        fused = trace["fused"]
        weights = trace["provider_weights"]
        total = sum(weights.values()) or 1.0

        print("  Module : HybridFusionEngine + WeightedVotingStrategy")
        print("          (src/q_guardian/quantum/fusion/)")
        print()
        print("  flow:  Rule Engine + IsolationForest + RandomForest + QSVM")
        print("         -> weighted soft voting -> fused confidence -> decision")
        print()
        print("  provider contributions (weighted soft vote):")
        print(
            f"    {'provider':<18} {'weight':>7} {'share':>6}  {'label':<10} "
            f"{'conf':>6} {'risk':>6}"
        )
        for pred in fused.source_predictions:
            w = weights.get(pred.provider_id, 1.0)
            share = w / total
            print(
                f"    {pred.provider_id:<18} {w:>7.2f} {_pct(share):>6}  "
                f"{pred.predicted_label:<10} {pred.confidence:>6.3f} "
                f"{pred.risk_score:>6.3f}"
            )
        print()
        print("  weighted soft vote (benign/threat across all providers):")
        for label, prob in sorted(fused.probabilities.items()):
            print(f"    P({label:<7}) = {prob:.4f}  {_bar(prob)}")
        _kv("Fused label", fused.predicted_label)
        _kv("Fused confidence", f"{fused.confidence:.4f}")
        _kv("Fused risk", f"{fused.risk_score:.4f}  (threat probability)")
        _kv("Strategy", fused.strategy_name)
        _kv("Reasoning", fused.reasoning_summary)

    # -- STEP 8 ------------------------------------------------------------
    def _render_step8(self, trace: dict[str, Any]) -> None:
        _header("STEP 8 - FINAL OUTPUT")
        fused = trace["fused"]
        assessment = trace["assessment"]
        decision = trace["decision"]
        resp = trace["response"]

        benign = fused.probabilities.get("benign", 0.0)
        threat = fused.probabilities.get("threat", 0.0)
        verdict = self._verdict_for(resp.action.value)
        _kv("Safe %", f"{benign * 100:.1f}%")
        _kv("Threat %", f"{threat * 100:.1f}%")
        _kv("Confidence", f"{fused.confidence:.4f}")
        _kv("Risk score", f"{assessment.risk_score:.4f}")
        _kv("Risk level", assessment.risk_level.value)
        _kv("Threat level", assessment.threat_score.threat_level.value)
        _kv("Severity", assessment.severity.severity.value)
        _kv(
            "Policy",
            f"{decision.policy_name} -> {decision.outcome.value} ({decision.action.value})",
        )
        _kv("Verdict", verdict)
        _kv("Action", resp.action.value)
        _kv("Assessment reasoning", "; ".join(assessment.reasoning))

    @staticmethod
    def _verdict_for(action: str) -> str:
        a = action.upper()
        if a in ("ALLOW", "LOG_ONLY"):
            return "SAFE"
        if a in ("WARN", "REVIEW", "MONITOR"):
            return "SUSPICIOUS"
        return "UNSAFE"

    # -- STEP 9 ------------------------------------------------------------
    def _render_step9(self, trace: dict[str, Any]) -> None:
        _header("STEP 9 - CODE TRACE")
        rows = [
            ("User prompt", "", "", ""),
            (
                "Preprocessing",
                "PromptNormalizer",
                "normalize",
                "src/q_guardian/security/pipeline.py",
            ),
            ("Validation", "PromptValidator", "validate", "src/q_guardian/security/pipeline.py"),
            (
                "Feature extraction",
                "PromptFeatureExtractor",
                "extract",
                "src/q_guardian/security/pipeline.py",
            ),
            (
                "Feature vector",
                "MLFeatureProvider",
                "extract_vector",
                "src/q_guardian/ml/feature_pipeline.py",
            ),
            ("Scaling", "StandardScaler", "transform", "sklearn.preprocessing"),
            ("Rule analysis", "RuleEngine", "analyze", "src/q_guardian/security/pipeline.py"),
            (
                "Classical ML",
                "RandomForestThreatClassifier",
                "predict",
                "src/q_guardian/ml/models/classifier.py",
            ),
            (
                "Classical ML",
                "IsolationForestDetector",
                "predict",
                "src/q_guardian/ml/models/anomaly.py",
            ),
            ("Quantum", "QSVMModel", "predict", "src/q_guardian/quantum/models/qsvm.py"),
            ("Fusion", "HybridFusionEngine", "fuse", "src/q_guardian/quantum/fusion/engine.py"),
            (
                "Fusion strategy",
                "WeightedVotingStrategy",
                "fuse",
                "src/q_guardian/quantum/fusion/strategies/weighted_voting.py",
            ),
            (
                "Risk",
                "RiskAssessmentEngine",
                "assess",
                "src/q_guardian/risk/assessment/risk_engine.py",
            ),
            ("Policy", "PolicyEngine", "evaluate", "src/q_guardian/risk/policy/policy_engine.py"),
            (
                "Response",
                "ResponseEngine",
                "process",
                "src/q_guardian/response/engine/response_engine.py",
            ),
        ]
        for i, (stage, cls, method, file) in enumerate(rows, start=1):
            if not cls:
                print(f"  {i:>2}. {stage}")
                continue
            print(f"  {i:>2}. {stage:<18} -> {cls}.{method}()   [{file}]")

        print()
        print("  execution order:")
        print("  " + " -> ".join(f"{n}.{m}()" for _, n, m, _ in rows[1:]))

    # -- STEP 10 -----------------------------------------------------------
    def _render_step10(self, trace: dict[str, Any]) -> None:
        names = trace["feature_names"]
        raw = trace["raw_vector"]
        importances = self.pipeline.rf.model.feature_importances_

        _header("STEP 10 - FEATURE EXPLANATION MODE")
        print("  Every feature below is extracted by real Q-Guardian code.")
        print("  'Importance' is the learned weight from the trained Random Forest.")
        print()
        for i, (name, value) in enumerate(zip(names, raw, strict=False), start=1):
            meta = feature_meta(name)
            importance = float(importances[i - 1]) if i - 1 < len(importances) else 0.0
            quantum = "YES (first 5 features)" if i - 1 < QUANTUM_FEATURE_COUNT else "no"
            print(f"  {i:>2}. {name}")
            _kv("Definition", meta["definition"], indent=4)
            _kv("Formula", meta["formula"], indent=4)
            _kv("Python variable", _variable_of(name), indent=4)
            _kv("Python function", _function_of(name), indent=4)
            _kv("Python file", _file_of(name), indent=4)
            _kv("Example value", f"{value:g}", indent=4)
            _kv("Importance (RF)", f"{importance:.4f}  {_bar(importance)}", indent=4)
            _kv("ML models using it", "RandomForest, IsolationForest (43-dim vector)", indent=4)
            _kv("Quantum models using it", quantum, indent=4)
            _kv("Why it matters", meta["why"], indent=4)
            print()

    # -- Mermaid -----------------------------------------------------------
    def render_mermaid(self) -> str:
        lines = [
            "flowchart TD",
            '    A["User Prompt"] --> B["PromptNormalizer.normalize()"]',
            '    B --> C["PromptValidator.validate()"]',
            '    C --> D["PromptFeatureExtractor.extract()"]',
            '    D --> E["MLFeatureProvider.extract_vector() -> 43-dim"]',
            '    E --> F["RuleEngine.analyze()"]',
            '    E --> G["StandardScaler.transform()"]',
            '    G --> H["RandomForestThreatClassifier.predict()"]',
            '    G --> I["IsolationForestDetector.predict()"]',
            '    G --> J["QSVMModel.predict()"]',
            '    F --> K["HybridFusionEngine.fuse()"]',
            "    H --> K",
            "    I --> K",
            "    J --> K",
            '    K --> L["RiskAssessmentEngine.assess()"]',
            '    L --> M["PolicyEngine.evaluate()"]',
            '    M --> N["ResponseEngine.process()"]',
            '    N --> O["FINAL VERDICT + ACTION"]',
        ]
        return "\n".join(lines) + "\n"

    # -- Orchestration -----------------------------------------------------
    async def run(self, prompt: str) -> None:
        p = self.pipeline
        trace: dict[str, Any] = {}

        self._render_step1(prompt)

        # Stage 2 - preprocessing
        t = time.monotonic()
        normalized = p.normalizer.normalize(prompt)
        trace["normalized"] = normalized
        self._render_step2(prompt, normalized)
        trace["t2_ms"] = (time.monotonic() - t) * 1000

        # Stage 3 - feature extraction
        t = time.monotonic()
        base = p.feature_extractor.extract(normalized)
        raw_vector = p.ml_features.extract_vector(normalized, base).features
        names = p.ml_features.feature_names
        scaled = p.scaler.transform(np.array([raw_vector], dtype=np.float64))[0]
        scaled_list = scaled.tolist()
        trace["base_features"] = base
        trace["feature_names"] = names
        trace["raw_vector"] = raw_vector
        trace["scaled_vector"] = scaled_list
        self._render_step3(trace)
        trace["t3_ms"] = (time.monotonic() - t) * 1000

        # Stage 4 - rule engine
        t = time.monotonic()
        findings = p.rule_engine.analyze(normalized, base)
        trace["rules_checked"] = len(p.rule_engine.list_rules(enabled_only=True))
        trace["findings"] = findings
        self._render_step4(trace)
        trace["t4_ms"] = (time.monotonic() - t) * 1000

        # Stage 5 - classical ML
        t = time.monotonic()
        anomaly = await p.anomaly.predict(scaled_list)
        rf = await p.rf.predict(scaled_list)
        arr = np.array([scaled_list], dtype=np.float64)
        votes: dict[str, int] = {}
        for tree in p.rf.model.estimators_:
            idx = int(tree.predict(arr)[0])
            label = p.rf._classes[idx]
            votes[label] = votes.get(label, 0) + 1
        trace["anomaly"] = anomaly
        trace["rf"] = rf
        trace["rf_votes"] = votes
        self._render_step5(trace)
        trace["t5_ms"] = (time.monotonic() - t) * 1000

        # Stage 6 - quantum pipeline
        t = time.monotonic()
        q_vec = scaled_list[:QUANTUM_FEATURE_COUNT]
        qr = await p.qsvm.predict(q_vec)
        enc = p._q_feature_map.encode(q_vec)
        circuit_info = p._q_kernel.get_circuit_info()
        sims = [
            (int(label), float(p._q_kernel.evaluate(q_vec, sv)))
            for sv, label in zip(p.qsvm.support_vectors, p.qsvm.support_labels, strict=False)
        ]
        trace["q_vector"] = q_vec
        trace["q"] = qr
        trace["q_encoding"] = enc
        trace["q_circuit_info"] = circuit_info
        trace["q_kernel_sims"] = sims
        self._render_step6(trace)
        trace["t6_ms"] = (time.monotonic() - t) * 1000

        # Stage 7 - hybrid fusion
        t = time.monotonic()
        fused = await p.fusion.fuse(
            prompt,
            features={"feature_vector": scaled_list},
            calibrate=True,
        )
        trace["fused"] = fused
        trace["provider_weights"] = dict(p.fusion._provider_weights)
        self._render_step7(trace)
        trace["t7_ms"] = (time.monotonic() - t) * 1000

        # Stage 8 - risk / policy / response
        t = time.monotonic()
        from q_guardian.risk.data import NormalizedPrediction

        npred = NormalizedPrediction(
            source_id=fused.fused_id,
            source_type="fused",
            model_name="hybrid-fusion",
            provider_id="fusion",
            predicted_label=fused.predicted_label,
            confidence=fused.confidence,
            probabilities={str(k): float(v) for k, v in fused.probabilities.items()},
            risk_score=fused.risk_score,
        )
        assessment = p.risk_engine.assess(npred)
        decision = p.policy_engine.evaluate(assessment)
        from q_guardian.response.data import (
            PolicyDecision as ResponsePolicyDecision,
        )
        from q_guardian.response.data import (
            ResponseRequest,
        )
        from q_guardian.response.data import (
            RiskAssessment as ResponseRiskAssessment,
        )
        from q_guardian.response.engine.response_engine import ResponseEngine

        resp = ResponseEngine().process(
            ResponseRequest(
                policy_decision=ResponsePolicyDecision(
                    outcome=decision.outcome.value,
                    action=decision.action.value,
                    severity=assessment.severity.severity.value,
                    risk_score=assessment.risk_score,
                ),
                risk_assessment=ResponseRiskAssessment(
                    risk_score=assessment.risk_score,
                    risk_level=assessment.risk_level.value,
                    threat_level=assessment.threat_score.threat_level.value,
                    confidence=assessment.confidence.normalized_confidence,
                    severity=assessment.severity.severity.value,
                ),
            )
        )
        trace["assessment"] = assessment
        trace["decision"] = decision
        trace["response"] = resp
        self._render_step8(trace)
        trace["t8_ms"] = (time.monotonic() - t) * 1000

        # Stage 9 - code trace
        self._render_step9(trace)

        _header("PERFORMANCE")
        total = sum(
            trace[k] for k in ("t2_ms", "t3_ms", "t4_ms", "t5_ms", "t6_ms", "t7_ms", "t8_ms")
        )
        for key, label in (
            ("t2_ms", "preprocessing"),
            ("t3_ms", "feature extraction"),
            ("t4_ms", "rule engine"),
            ("t5_ms", "classical ML"),
            ("t6_ms", "quantum pipeline"),
            ("t7_ms", "hybrid fusion"),
            ("t8_ms", "risk + policy + response"),
        ):
            ms = trace[key]
            print(f"    {label:<26} {ms:>10.2f} ms  {(ms / total * 100 if total else 0):>5.1f} %")
        print(f"    {'TOTAL':<26} {total:>10.2f} ms")


async def _run_prompt(runner: ExplainableRunner, prompt: str, explain_features: bool) -> None:
    await runner.run(prompt)
    if explain_features:
        trace = {
            "feature_names": runner.pipeline.ml_features.feature_names,
            "raw_vector": runner.pipeline.ml_features.extract_vector(
                runner.pipeline.normalizer.normalize(prompt),
                runner.pipeline.feature_extractor.extract(
                    runner.pipeline.normalizer.normalize(prompt)
                ),
            ).features,
        }
        runner._render_step10(trace)


async def _main() -> None:
    args = sys.argv[1:]
    explain_features = "--explain-features" in args
    args = [a for a in args if a != "--explain-features"]
    mermaid_path: str | None = None
    if "--export-mermaid" in args:
        i = args.index("--export-mermaid")
        if i + 1 < len(args) and not args[i + 1].startswith("--"):
            mermaid_path = args[i + 1]
            del args[i : i + 2]
        else:
            mermaid_path = "examples/q_guardian_runtime_flowchart.mmd"
            del args[i]

    prompts = [a for a in args if not a.startswith("--")]

    runner = ExplainableRunner()

    if mermaid_path:
        out = Path(mermaid_path)
        out.write_text(runner.render_mermaid(), encoding="utf-8")
        print(f"\nMermaid flowchart exported to {out}")

    if prompts:
        for prompt in prompts:
            await _run_prompt(runner, prompt, explain_features)
        return

    print("Interactive mode - type a prompt to analyze (empty line = exit):")
    while True:
        try:
            prompt = input("  prompt> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            break
        await _run_prompt(runner, prompt, explain_features)


if __name__ == "__main__":
    asyncio.run(_main())
