"""LangGraph adapter for Q-Guardian.

Integrates Q-Guardian's security pipeline with LangGraph framework,
providing security scanning for LangGraph graph inputs, outputs,
states, and messages.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from q_guardian.adapters.base import Adapter
from q_guardian.security.encoding import detect_all_encodings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph import StateGraph
    from langgraph.graph.state import CompiledStateGraph

    from q_guardian.sdk.guardian import Guardian

# Runtime availability probe for the optional LangGraph dependency.
# Annotation-only symbols are imported under TYPE_CHECKING above; with
# ``from __future__ import annotations`` they never evaluate at runtime,
# so no object-sentinel fallbacks are needed when the package is absent.
try:
    import langchain_core  # noqa: F401
    import langgraph  # noqa: F401

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    LANGGRAPH_AVAILABLE = False

logger = logging.getLogger("q_guardian.adapters.langgraph")


class LangGraphSecurityError(Exception):
    """Raised when LangGraph execution is blocked by security policy."""

    def __init__(self, message: str, findings: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.findings = findings or []


class _SecuredCompiledGraph:
    """Duck-typed security wrapper around a compiled LangGraph state graph.

    Delegates every attribute to the wrapped compiled graph while
    intercepting ``invoke`` / ``ainvoke`` / ``stream`` / ``astream`` so
    inputs are scanned before execution and outputs (including each
    stream chunk) are scanned after. The wrapped graph instance is never
    mutated, preserving the original object for the framework.
    """

    def __init__(
        self,
        compiled: CompiledStateGraph[Any, None, Any, Any],
        adapter: LangGraphAdapter,
    ) -> None:
        self._compiled = compiled
        self._adapter = adapter

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped compiled graph."""
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._compiled, name)

    def invoke(self, input_data: Any, config: Any = None, **kwargs: Any) -> Any:
        """Scan input, execute synchronously, then scan output."""
        self._adapter._scan_and_check_sync(input_data, "input")
        result = self._compiled.invoke(input_data, config, **kwargs)
        self._adapter._scan_and_check_sync(result, "output")
        return result

    async def ainvoke(self, input_data: Any, config: Any = None, **kwargs: Any) -> Any:
        """Scan input, execute asynchronously, then scan output."""
        await self._adapter._scan_and_check(input_data, "input")
        result = await self._compiled.ainvoke(input_data, config, **kwargs)
        await self._adapter._scan_and_check(result, "output")
        return result

    def stream(self, input_data: Any, config: Any = None, **kwargs: Any) -> Iterator[Any]:
        """Synchronous streaming with per-chunk output scanning.

        Chunks arrive from the underlying synchronous iterator and are
        scanned with the synchronous scanner before being yielded.
        """
        self._adapter._scan_and_check_sync(input_data, "input")
        for chunk in self._compiled.stream(input_data, config, **kwargs):
            self._adapter._scan_and_check_sync(chunk, "stream_chunk")
            yield chunk

    async def astream(
        self, input_data: Any, config: Any = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        """Asynchronous streaming with per-chunk output scanning."""
        await self._adapter._scan_and_check(input_data, "input")
        async for chunk in self._compiled.astream(input_data, config, **kwargs):
            await self._adapter._scan_and_check(chunk, "stream_chunk")
            yield chunk


class LangGraphAdapter(Adapter):
    """Adapter for LangGraph framework integration.

    Provides security scanning for LangGraph graph inputs, outputs,
    states, messages, and node execution.
    """

    def __init__(
        self,
        guardian: Guardian | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the LangGraph adapter.

        Args:
            guardian: Optional Guardian instance for security scanning.
            config: Optional configuration dictionary.
        """
        if not LANGGRAPH_AVAILABLE:
            raise RuntimeError(
                "LangGraph is not installed. Install with: pip install 'q-guardian[langgraph]'"
            )

        self._guardian = guardian
        self._config = config or {}
        self._compiled_graph: _SecuredCompiledGraph | None = None
        self._checkpointer: Any = None

    @property
    def name(self) -> str:
        return "langgraph"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def framework_name(self) -> str:
        return "LangGraph"

    async def initialize(self, context: Any) -> None:
        """Initialize the adapter with framework context.

        Args:
            context: The shared framework context.
        """
        self._context = context
        logger.info("LangGraph adapter initialized")

    async def shutdown(self) -> None:
        """Shut down the adapter and release resources."""
        self._compiled_graph = None
        self._checkpointer = None
        logger.info("LangGraph adapter shut down")

    async def connect_agent(self, agent_config: dict[str, Any]) -> Any:
        """Connect an AI agent to the security framework.

        Args:
            agent_config: Configuration for the agent connection.
                Expected keys: 'graph' (StateGraph), 'checkpointer' (optional)

        Returns:
            Compiled graph with security wrapping.
        """
        if not LANGGRAPH_AVAILABLE:
            raise RuntimeError(
                "LangGraph is not installed. Install with: pip install 'q-guardian[langgraph]'"
            )

        graph = agent_config.get("graph")
        if graph is None:
            raise ValueError("agent_config must contain 'graph' (StateGraph instance)")

        checkpointer = agent_config.get("checkpointer")
        compiled = self.compile_graph(graph, checkpointer=checkpointer)
        self._compiled_graph = compiled
        return compiled

    async def process_prompt(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        """Process a prompt through the security pipeline.

        Args:
            prompt: The prompt text to process.
            context: Additional processing context.

        Returns:
            Processing result dictionary with security findings.
        """
        from q_guardian.security.models import PromptAnalysis
        from q_guardian.security.pipeline import PromptNormalizer, PromptValidator, RuleEngine

        # Normalize and validate
        normalizer = PromptNormalizer()
        validator = PromptValidator()

        normalized = normalizer.normalize(prompt)
        validation_status, validation_errors = validator.validate(normalized)

        # Extract features
        from q_guardian.security.pipeline import PromptFeatureExtractor

        feature_extractor = PromptFeatureExtractor()
        features = feature_extractor.extract(normalized)

        # Rule analysis
        findings = RuleEngine().analyze(normalized, features)

        # Build analysis
        analysis = PromptAnalysis(
            original_prompt=prompt,
            normalized_prompt=normalized,
            is_valid=(validation_status.value == "valid"),
            validation_status=validation_status,
            validation_errors=validation_errors,
            features=features,
            findings=findings,
        )

        # Decision
        from q_guardian.security.decision import SecurityDecisionEngine

        decision_engine = SecurityDecisionEngine()
        decision_engine.decide(analysis)

        return analysis.model_dump()

    async def handle_response(self, response: Any) -> dict[str, Any]:
        """Handle a response from the AI framework.

        Args:
            response: The raw response from the AI framework.

        Returns:
            Processed response dictionary.
        """
        # Extract text content from response
        text_content = self._extract_text_content(response)
        return await self.process_prompt(text_content, {})

    async def extract_features(self, data: Any) -> dict[str, Any]:
        """Extract security-relevant features from framework data.

        Args:
            data: Raw data from the AI framework.

        Returns:
            Extracted features dictionary.
        """
        from q_guardian.security.homoglyph import analyze_homoglyphs

        text_content = self._extract_text_content(data)
        if not text_content:
            return {}

        features: dict[str, Any] = {}

        # Basic features
        features["length"] = len(text_content)
        features["word_count"] = len(text_content.split())
        features["line_count"] = text_content.count("\n") + 1

        # Encoding detection
        encoding_candidates = detect_all_encodings(text_content)
        features["encoding_candidates"] = [
            {
                "encoding": c.encoding,
                "confidence": c.confidence,
                "decoded_preview": c.metadata.get("decoded_preview", "")[:200],
            }
            for c in encoding_candidates
        ]

        # Homoglyph detection
        homoglyph_results = analyze_homoglyphs(text_content)
        features["homoglyph"] = {
            "has_confusables": homoglyph_results["has_confusables"],
            "has_mixed_script": homoglyph_results["has_mixed_script"],
            "confusables_count": len(homoglyph_results["confusables"]),
            "mixed_script_count": len(homoglyph_results["mixed_script"]),
        }

        return features

    # ============================================================
    # LangGraph-specific APIs
    # ============================================================

    def compile_graph(
        self,
        graph: StateGraph[Any],
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        **kwargs: Any,
    ) -> _SecuredCompiledGraph:
        """Compile a LangGraph StateGraph with security wrapping.

        Args:
            graph: The StateGraph to compile.
            checkpointer: Optional checkpointer for persistence.
            interrupt_before: List of node names to interrupt before.
            interrupt_after: List of node names to interrupt after.
            **kwargs: Additional arguments passed to graph.compile().

        Returns:
            Compiled graph with security wrapping.
        """
        if not LANGGRAPH_AVAILABLE:
            raise RuntimeError("LangGraph is not installed")

        # Wrap node functions for security scanning
        self._wrap_graph_nodes(graph)

        compile_kwargs: dict[str, Any] = {}
        if checkpointer is not None:
            compile_kwargs["checkpointer"] = checkpointer
        if interrupt_before:
            compile_kwargs["interrupt_before"] = interrupt_before
        if interrupt_after:
            compile_kwargs["interrupt_after"] = interrupt_after
        compile_kwargs.update(kwargs)

        compiled = graph.compile(**compile_kwargs)

        # Wrap the compiled graph for security
        self._compiled_graph = self._wrap_compiled_graph(compiled)
        return self._compiled_graph

    def wrap_graph(
        self, compiled_graph: CompiledStateGraph[Any, None, Any, Any]
    ) -> _SecuredCompiledGraph:
        """Wrap an already compiled graph with security scanning.

        Args:
            compiled_graph: Pre-compiled LangGraph graph.

        Returns:
            Wrapped graph with security scanning.
        """
        self._compiled_graph = self._wrap_compiled_graph(compiled_graph)
        return self._compiled_graph

    async def scan_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """Scan graph input state for security threats.

        Args:
            state: Input state dictionary.

        Returns:
            Security analysis result.
        """
        return await self._scan_state(state, "input")

    async def scan_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """Scan graph output state for security threats.

        Args:
            state: Output state dictionary.

        Returns:
            Security analysis result.
        """
        return await self._scan_state(state, "output")

    async def scan_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Scan graph state for security threats.

        Args:
            state: State dictionary to scan.

        Returns:
            Security analysis result.
        """
        return await self._scan_state(state, "state")

    # ============================================================
    # Internal Implementation
    # ============================================================

    def _wrap_graph_nodes(self, graph: StateGraph[Any]) -> StateGraph[Any]:
        """Wrap node functions in a graph for security scanning.

        This creates a new graph with wrapped node functions.
        """
        # LangGraph doesn't easily allow node wrapping after graph creation.
        # We handle security at the compiled graph level instead.
        return graph

    def _wrap_compiled_graph(
        self, compiled: CompiledStateGraph[Any, None, Any, Any]
    ) -> _SecuredCompiledGraph:
        """Wrap a compiled graph with security scanning.

        Returns a duck-typed wrapper that intercepts the invoke/stream
        entry points; the original compiled graph object is not mutated.
        """
        return _SecuredCompiledGraph(compiled, self)

    async def _scan_and_check(self, data: Any, source: str) -> dict[str, Any]:
        """Scan data and raise exception if blocked."""
        result = await self._scan_text(self._extract_text_content(data), source)
        if result.get("decision") == "block":
            raise LangGraphSecurityError(
                f"Security policy violation in {source}",
                result.get("findings", []),
            )
        return result

    def _scan_and_check_sync(self, data: Any, source: str) -> dict[str, Any]:
        """Synchronous version of scan and check."""
        result = asyncio.run(self._scan_text(self._extract_text_content(data), source))
        if result.get("decision") == "block":
            raise LangGraphSecurityError(
                f"Security policy violation in {source}",
                result.get("findings", []),
            )
        return result

    async def _scan_state(self, state: dict[str, Any], source: str) -> dict[str, Any]:
        """Scan a state dictionary for security threats."""
        # Extract text from state values
        text_parts = []
        for key, value in state.items():
            if isinstance(value, str):
                text_parts.append(f"{key}: {value}")
            elif isinstance(value, (list, dict)):
                text_parts.append(f"{key}: {self._extract_text_content(value)}")

        text_content = "\n".join(text_parts)
        return await self._scan_text(text_content, source)

    async def _scan_text(self, text: str, source: str) -> dict[str, Any]:
        """Scan text content using the existing security pipeline."""
        from q_guardian.security.decision import SecurityDecisionEngine
        from q_guardian.security.homoglyph import analyze_homoglyphs
        from q_guardian.security.models import PromptAnalysis
        from q_guardian.security.pipeline import (
            PromptFeatureExtractor,
            PromptNormalizer,
            PromptValidator,
            RuleEngine,
        )

        if not text or not text.strip():
            return {"decision": "allow", "risk_score": 0.0, "findings": []}

        # Normalize and validate
        normalizer = PromptNormalizer()
        validator = PromptValidator()

        normalized = normalizer.normalize(text)
        validation_status, validation_errors = validator.validate(normalized)

        # Extract features
        feature_extractor = PromptFeatureExtractor()
        features = feature_extractor.extract(normalized)

        # Add encoding and homoglyph features
        from q_guardian.security.encoding import detect_all_encodings

        encoding_candidates = detect_all_encodings(text)
        homoglyph_results = analyze_homoglyphs(text)

        # Add to features (PromptFeatures has no declared fields for these;
        # provenance lives in metadata, matching the crewai adapter and the
        # provenance-aware scanning path)
        features.metadata["encoding_candidates"] = [
            {
                "encoding": c.encoding,
                "confidence": c.confidence,
                "decoded_preview": c.metadata.get("decoded_preview", "")[:200],
            }
            for c in encoding_candidates
        ]
        features.metadata["homoglyph"] = {
            "has_confusables": homoglyph_results["has_confusables"],
            "has_mixed_script": homoglyph_results["has_mixed_script"],
        }

        # Rule analysis
        engine = RuleEngine()
        findings = engine.analyze(normalized, features)

        # Build analysis
        analysis = PromptAnalysis(
            original_prompt=text,
            normalized_prompt=normalized,
            is_valid=(validation_status.value == "valid"),
            validation_status=validation_status,
            validation_errors=validation_errors,
            features=features,
            findings=findings,
        )

        # Decision
        decision_engine = SecurityDecisionEngine()
        decision_engine.decide(analysis)

        return {
            "decision": analysis.decision.value,
            "risk_score": analysis.risk_score,
            "findings": [f.model_dump() for f in analysis.findings],
            "encoding_context": {
                "encoding_candidates": [
                    {
                        "encoding": c.encoding,
                        "confidence": c.confidence,
                        "decoded_preview": c.metadata.get("decoded_preview", "")[:200],
                    }
                    for c in encoding_candidates
                ],
                "homoglyph": {
                    "has_confusables": homoglyph_results["has_confusables"],
                    "has_mixed_script": homoglyph_results["has_mixed_script"],
                },
            },
        }

    def _extract_text_content(self, data: Any) -> str:
        """Extract text content from various data types."""
        if isinstance(data, str):
            return data
        elif isinstance(data, dict):
            parts = []
            for key, value in data.items():
                if isinstance(value, str):
                    parts.append(f"{key}: {value}")
                elif isinstance(value, (list, dict)):
                    parts.append(f"{key}: {self._extract_text_content(value)}")
                elif hasattr(data, "content") and isinstance(data.content, str):
                    parts.append(f"{key}: {data.content}")
            return "\n".join(parts)
        elif isinstance(data, list):
            parts = []
            for item in data:
                parts.append(self._extract_text_content(item))
            return "\n".join(parts)
        elif hasattr(data, "content") and isinstance(data.content, str):
            return data.content
        elif hasattr(data, "content") and isinstance(data.content, list):
            # Structured content (e.g., [{"type": "text", "text": "..."}])
            parts = []
            for item in data.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return "\n".join(parts)
        elif hasattr(data, "content"):
            return str(data.content)
        return str(data)

    def _extract_messages_text(self, messages: list[Any]) -> str:
        """Extract text from a list of LangChain messages."""
        if not messages:
            return ""

        parts = []
        for _msg in messages:
            if hasattr(_msg, "content"):
                content = _msg.content
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            parts.append(item.get("text", ""))
        return "\n".join(parts)

    # ============================================================
    # Indirect injection: provenance-aware state scanning (P3-5)
    # ============================================================

    async def scan_state_with_provenance(
        self,
        state: dict[str, Any],
        untrusted_keys: list[str],
        source: str = "state",
    ) -> dict[str, Any]:
        """Scan graph state with provenance-aware indirect injection analysis.

        Values under ``untrusted_keys`` are treated as untrusted external
        content (tool outputs, retrieved documents, ...) and analyzed by
        the ``ii-*`` rules in addition to the standard direct rules.
        Behavior is additive: keys not listed keep their existing handling,
        and an empty ``untrusted_keys`` list yields the same result as a
        plain state scan.

        This method is intentionally self-contained and does not rely on
        the legacy internal text-scanning helpers.

        Args:
            state: The graph state dictionary.
            untrusted_keys: State keys whose values carry untrusted
                external content. String values and lists of strings are
                supported; other value types are stringified.
            source: Label describing where the state came from.

        Returns:
            Scan result dictionary with decision, risk_score, findings,
            source, encoding_context, and (when segments were scanned)
            indirect_context keys.

        Raises:
            ValueError: If ``untrusted_keys`` is empty or state is empty.
        """
        from q_guardian.security.config import IndirectInjectionConfig
        from q_guardian.security.decision import SecurityDecisionEngine
        from q_guardian.security.homoglyph import analyze_homoglyphs
        from q_guardian.security.indirect import (
            ContentSegment,
            SourceType,
            build_untrusted_context,
        )
        from q_guardian.security.models import PromptAnalysis
        from q_guardian.security.pipeline import (
            PromptFeatureExtractor,
            PromptNormalizer,
            PromptValidator,
            RuleEngine,
        )

        if not untrusted_keys:
            raise ValueError("untrusted_keys must contain at least one state key")
        if not state:
            raise ValueError("state must not be empty")

        segments: list[ContentSegment] = []
        for position, key in enumerate(untrusted_keys):
            if key not in state:
                continue
            value = state[key]
            texts = (
                [str(item) for item in value]
                if isinstance(value, list)
                else [value if isinstance(value, str) else str(value)]
            )
            for text in texts:
                if text.strip():
                    segments.append(
                        ContentSegment(
                            content=text,
                            source_type=SourceType.TOOL_OUTPUT,
                            source_id=key,
                            position=position,
                        )
                    )

        direct_text = "\n".join(str(v) for k, v in state.items() if isinstance(v, str))
        if not direct_text.strip():
            return {"decision": "allow", "risk_score": 0.0, "findings": [], "source": source}

        normalizer = PromptNormalizer()
        validator = PromptValidator()
        normalized = normalizer.normalize(direct_text)
        validation_status, validation_errors = validator.validate(normalized)

        feature_extractor = PromptFeatureExtractor()
        features = feature_extractor.extract(normalized)

        homoglyph_results = analyze_homoglyphs(normalized)
        features.metadata["homoglyph"] = {
            "has_confusables": homoglyph_results["has_confusables"],
            "has_mixed_script": homoglyph_results["has_mixed_script"],
        }

        indirect_context: dict[str, Any] | None = None
        if segments:
            indirect_config = IndirectInjectionConfig()
            indirect_context = build_untrusted_context(segments, indirect_config)
            features.metadata["untrusted_context"] = indirect_context

        engine = RuleEngine()
        findings = engine.analyze(normalized, features)

        analysis = PromptAnalysis(
            original_prompt=direct_text,
            normalized_prompt=normalized,
            is_valid=(validation_status.value == "valid"),
            validation_status=validation_status,
            validation_errors=validation_errors,
            features=features,
            findings=findings,
        )
        SecurityDecisionEngine().decide(analysis)

        result: dict[str, Any] = {
            "decision": analysis.decision.value,
            "risk_score": analysis.risk_score,
            "findings": [f.model_dump() for f in analysis.findings],
            "recommendation": analysis.recommendation,
            "source": source,
            "encoding_context": {
                "encoding_candidates": [
                    {
                        "encoding": c.encoding,
                        "confidence": c.confidence,
                        "decoded_preview": c.metadata.get("decoded_preview", "")[:200],
                    }
                    for c in detect_all_encodings(normalized)
                ],
                "homoglyph": {
                    "has_confusables": homoglyph_results["has_confusables"],
                    "has_mixed_script": homoglyph_results["has_mixed_script"],
                },
            },
        }
        if indirect_context is not None:
            result["indirect_context"] = {
                "segments_scanned": len(indirect_context.get("segments", [])),
                "segments_omitted": indirect_context.get("segments_omitted", 0),
                "trusted_count": indirect_context.get("trusted_count", 0),
                "indirect_findings_count": sum(
                    1 for f in analysis.findings if f.rule_id.startswith("ii-")
                ),
            }
        return result

    # ============================================================
    # Output monitoring: direction-gated output scans (P3-3)
    # ============================================================

    @staticmethod
    def _output_text_of(data: Any, _depth: int = 0) -> str:
        """Extract scannable text from arbitrary LangGraph/framework data.

        Self-contained helper for the P3-3 output-monitoring methods. It
        intentionally does NOT reuse ``_extract_text_content`` (whose
        recursive shadowing makes it unusable) and mirrors the provenance
        method's self-containment policy.

        Args:
            data: Arbitrary output data (string, object with ``raw`` or
                ``content``, dict, list, ...).
            _depth: Internal recursion depth guard.

        Returns:
            Extracted text content (may be empty).
        """
        if data is None or _depth > 8:
            return ""
        if isinstance(data, str):
            return data
        if isinstance(data, bool):
            return str(data)
        if isinstance(data, (int, float)):
            return str(data)
        raw = getattr(data, "raw", None)
        if isinstance(raw, str):
            return raw
        content = getattr(data, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        if isinstance(data, dict):
            return "\n".join(
                part
                for part in (
                    LangGraphAdapter._output_text_of(value, _depth + 1) for value in data.values()
                )
                if part
            )
        if isinstance(data, (list, tuple)):
            return "\n".join(
                part
                for part in (LangGraphAdapter._output_text_of(item, _depth + 1) for item in data)
                if part
            )
        return ""

    async def scan_output_text(
        self,
        output: Any,
        *,
        source: str = "output",
        context_segments: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Scan agent output text through output monitoring (P3-3).

        Runs the shared pipeline in the output direction: the
        direction-gated ``om-*`` rules fire on leakage, disclosure,
        sensitive-data/credential exposure, actionable commands,
        obfuscated payloads, and propagation of untrusted content.
        Behavior is additive — no existing scanning path is modified.

        Args:
            output: Output text or arbitrary framework object with
                extractable text (``raw`` / ``content`` / containers).
            source: Label describing where the output came from.
            context_segments: Optional untrusted input segments
                (``ContentSegment`` or JSON-safe dicts) correlated against
                the output by om-007.

        Returns:
            Scan result dictionary with decision, risk_score, findings,
            source, encoding_context and (when active) output_context keys.

        Raises:
            ValueError: If the extracted output text is empty.
        """
        from q_guardian.output.monitor import build_output_context, resolve_output_config
        from q_guardian.security.decision import SecurityDecisionEngine
        from q_guardian.security.homoglyph import analyze_homoglyphs
        from q_guardian.security.indirect import ContentSegment
        from q_guardian.security.models import PromptAnalysis
        from q_guardian.security.pipeline import (
            PromptFeatureExtractor,
            PromptNormalizer,
            PromptValidator,
            RuleEngine,
        )

        text = self._output_text_of(output)
        if not text.strip():
            raise ValueError("output must contain scannable text")

        config = resolve_output_config(self._config.get("output_config"))
        truncated = False
        if len(text) > config.max_output_length:
            text = text[: config.max_output_length]
            truncated = True

        normalizer = PromptNormalizer()
        validator = PromptValidator()
        normalized = normalizer.normalize(text)
        validation_status, validation_errors = validator.validate(normalized)

        feature_extractor = PromptFeatureExtractor()
        features = feature_extractor.extract(normalized)

        homoglyph_results = analyze_homoglyphs(normalized)
        features.metadata["homoglyph"] = {
            "has_confusables": homoglyph_results["has_confusables"],
            "has_mixed_script": homoglyph_results["has_mixed_script"],
        }

        output_active = False
        segments: list[ContentSegment] | None = None
        if context_segments:
            segments = [
                seg if isinstance(seg, ContentSegment) else ContentSegment.model_validate(seg)
                for seg in context_segments
            ]
        if config.enabled:
            features.metadata["output_context"] = build_output_context(
                normalized,
                source,
                config,
                context_segments=segments,
            )
            output_active = True

        engine = RuleEngine()
        findings = engine.analyze(normalized, features)

        analysis = PromptAnalysis(
            original_prompt=text,
            normalized_prompt=normalized,
            is_valid=(validation_status.value == "valid"),
            validation_status=validation_status,
            validation_errors=validation_errors,
            features=features,
            findings=findings,
        )
        SecurityDecisionEngine().decide(analysis)

        result: dict[str, Any] = {
            "decision": analysis.decision.value,
            "risk_score": analysis.risk_score,
            "findings": [f.model_dump() for f in analysis.findings],
            "recommendation": analysis.recommendation,
            "source": source,
            "encoding_context": {
                "encoding_candidates": [
                    {
                        "encoding": c.encoding,
                        "confidence": c.confidence,
                        "decoded_preview": c.metadata.get("decoded_preview", "")[:200],
                    }
                    for c in detect_all_encodings(normalized)
                ],
                "homoglyph": {
                    "has_confusables": homoglyph_results["has_confusables"],
                    "has_mixed_script": homoglyph_results["has_mixed_script"],
                },
            },
        }
        if output_active:
            result["output_context"] = {
                "source_label": source,
                "truncated": truncated,
                "output_findings_count": sum(
                    1 for f in analysis.findings if f.rule_id.startswith("om-")
                ),
            }
        return result

    async def scan_output_state(
        self,
        state: dict[str, Any],
        untrusted_keys: list[str] | None = None,
        *,
        source: str = "state_output",
    ) -> dict[str, Any]:
        """Scan graph state in the output direction (P3-3).

        Aggregates all string state values into one output text and runs
        :meth:`scan_output_text` over it. When ``untrusted_keys`` is given,
        the values under those keys are additionally treated as untrusted
        input segments for om-007 propagation correlation.

        Args:
            state: The graph state dictionary.
            untrusted_keys: Optional state keys whose values carry
                untrusted external content to correlate.
            source: Label describing where the state came from.

        Returns:
            The same result dictionary as :meth:`scan_output_text`.

        Raises:
            ValueError: If the state contains no string values.
        """
        if not state:
            raise ValueError("state must not be empty")

        text = "\n".join(str(v) for v in state.values() if isinstance(v, str))
        if not text.strip():
            raise ValueError("state must contain at least one non-empty string value")

        segments: list[dict[str, Any]] | None = None
        if untrusted_keys:
            segments = [
                {"content": str(state[key]), "source_type": "tool_output", "source_id": key}
                for key in untrusted_keys
                if key in state and str(state[key]).strip()
            ] or None

        return await self.scan_output_text(text, source=source, context_segments=segments)

    async def aggregate_stream_output(
        self,
        chunks: Any,
        *,
        source: str = "stream_output",
    ) -> dict[str, Any]:
        """Aggregate a token stream and scan it end-of-stream (P3-3).

        Collects all chunks into one buffer, then performs a single
        output-direction scan of the complete aggregated text. Blocking on
        the final aggregate prevents partial-payload evasion where a
        credential is split across chunks. Chunks are concatenated without
        separators so tokens split across chunk boundaries reassemble
        exactly as the model emitted them.

        Args:
            chunks: Iterable (or async iterable) of stream chunks; each may
                be a plain string or an object with extractable text.
            source: Label describing where the stream came from.

        Returns:
            The same result dictionary as :meth:`scan_output_text`, plus
            ``aggregated_length`` and (when caps were hit)
            ``stream_truncated`` keys. Collection enforces strict limits:
            at most ``max_stream_chunks`` chunks (default 10,000) and at
            most ``max_output_length`` aggregated characters; excess
            content is dropped and flagged rather than buffered.

        Raises:
            LangGraphSecurityError: If the aggregated output violates policy.
            ValueError: If no chunk yields any text.
        """
        from q_guardian.output.monitor import resolve_output_config

        config = resolve_output_config(self._config.get("output_config"))
        collected: list[str] = []
        total_length = 0
        chunk_count = 0
        truncated_stream = False

        def _collect(piece: str) -> bool:
            """Append a piece under strict size/chunk caps; False when full."""
            nonlocal total_length, truncated_stream
            remaining = config.max_output_length - total_length
            if remaining <= 0:
                truncated_stream = True
                return False
            collected.append(piece[:remaining])
            total_length += len(collected[-1])
            if total_length >= config.max_output_length:
                truncated_stream = True
                return False
            return True

        async def _drain(chunk_iter: Any, max_chunks: int) -> None:
            nonlocal chunk_count, truncated_stream
            while True:
                try:
                    chunk = await chunk_iter.__anext__()
                except StopAsyncIteration:
                    break
                piece = self._output_text_of(chunk)
                chunk_count += 1
                if piece:
                    _collect(piece)
                if chunk_count >= max_chunks:
                    truncated_stream = True
                    break

        max_chunks = int(self._config.get("max_stream_chunks", 10_000))
        if hasattr(chunks, "__anext__") or hasattr(chunks, "__aiter__"):
            await _drain(chunks, max_chunks)
        else:
            for chunk in chunks:
                piece = self._output_text_of(chunk)
                chunk_count += 1
                if piece and not _collect(piece):
                    break
                if chunk_count >= max_chunks:
                    truncated_stream = True
                    break

        aggregated = "".join(collected)
        result = await self.scan_output_text(aggregated, source=source)
        result["aggregated_length"] = len(aggregated)
        if truncated_stream:
            result["stream_truncated"] = True
        if result.get("decision") == "block":
            raise LangGraphSecurityError(
                "Blocked by Q-Guardian security policy (aggregated stream output)",
                findings=result.get("findings"),
            )
        return result

    def health(self) -> dict[str, Any]:
        """Return adapter health status."""
        return {
            "status": "healthy",
            "adapter": self.name,
            "version": self.version,
            "framework": self.framework_name,
            "langgraph_available": LANGGRAPH_AVAILABLE,
            "compiled_graph_ready": self._compiled_graph is not None,
        }

    def configuration(self) -> dict[str, Any]:
        """Return adapter configuration schema."""
        return {
            "encoding_detection_enabled": self._config.get("encoding_detection_enabled", True),
            "max_decode_depth": self._config.get("max_decode_depth", 3),
            "max_decoded_length": self._config.get("max_decoded_length", 50000),
        }


def create_langgraph_adapter(
    guardian: Guardian | None = None,
    config: dict[str, Any] | None = None,
) -> LangGraphAdapter:
    """Factory function to create a LangGraph adapter.

    Args:
        guardian: Optional Guardian instance for security scanning.
        config: Optional configuration dictionary.

    Returns:
        Configured LangGraphAdapter instance.
    """
    return LangGraphAdapter(guardian=guardian, config=config)
