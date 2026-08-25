"""CrewAI adapter for Q-Guardian.

Integrates Q-Guardian's security pipeline with the CrewAI framework,
providing security scanning for CrewAI crews, agents, tasks, kickoff
inputs/outputs, task guardrails, and tools.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import TYPE_CHECKING, Any

from q_guardian.adapters.base import Adapter
from q_guardian.security.encoding import detect_all_encodings
from q_guardian.security.indirect import (
    ContentSegment,
    IndirectInjectionConfig,
    SourceType,
    build_untrusted_context,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from q_guardian.events.bus import EventBus
    from q_guardian.framework.context import FrameworkContext
    from q_guardian.sdk.guardian import Guardian
    from q_guardian.security.config import OutputMonitoringConfig

try:
    from crewai import Crew, Process
    from crewai.tools import BaseTool

    CREWAI_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    Crew = object  # type: ignore[assignment,misc]
    Process = object  # type: ignore[assignment,misc]
    BaseTool = object  # type: ignore[assignment,misc]
    CREWAI_AVAILABLE = False

logger = logging.getLogger("q_guardian.adapters.crewai")

_BLOCKED_MESSAGE = "Blocked by Q-Guardian security policy"

# Source labels that represent agent/tool OUTPUT (as opposed to user
# inputs). When the adapter-level ``output_monitoring`` flag is enabled,
# only scans carrying one of these labels are analyzed by the
# direction-gated ``om-*`` rules; input scans keep prompt-direction
# behavior (including P3-5 indirect injection analysis).
_OUTPUT_SOURCE_LABELS: frozenset[str] = frozenset(
    {"output", "task_output", "tool_output", "stream_output"}
)


def _resolve_indirect_config(raw: Any) -> IndirectInjectionConfig:
    """Coerce adapter config into an ``IndirectInjectionConfig``."""
    if isinstance(raw, IndirectInjectionConfig):
        return raw
    if isinstance(raw, dict):
        return IndirectInjectionConfig.model_validate(raw)
    return IndirectInjectionConfig()


def _resolve_output_config(raw: Any) -> OutputMonitoringConfig:
    """Coerce adapter config into an ``OutputMonitoringConfig`` (P3-3)."""
    from q_guardian.output.monitor import resolve_output_config

    return resolve_output_config(raw)


class CrewAISecurityError(Exception):
    """Raised when CrewAI execution is blocked by security policy."""

    def __init__(self, message: str, findings: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.findings = findings or []


class SecuredCrewProxy:
    """Security proxy around a CrewAI ``Crew`` instance.

    Exposes kickoff-style methods that scan inputs before execution and
    outputs after execution. All other attribute access is delegated to
    the wrapped crew.
    """

    def __init__(self, crew: Any, adapter: CrewAIAdapter) -> None:
        self._crew_ref: Any = crew
        self._adapter: CrewAIAdapter = adapter

    @property
    def crew(self) -> Any:
        """Return the wrapped (unsecured) crew."""
        return self._crew_ref

    @property
    def secured(self) -> bool:
        """Always True; marks this object as a security wrapper."""
        return True

    def kickoff(
        self,
        inputs: dict[str, Any] | None = None,
        untrusted_keys: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Run a security-scanned synchronous crew kickoff.

        Inputs are scanned (and threat events published) before execution;
        outputs are scanned after execution.

        Args:
            inputs: Kickoff inputs scanned before execution.
            untrusted_keys: Optional keys of ``inputs`` whose values carry
                untrusted external content. Either a list of key names or
                a mapping of key name to ``SourceType`` value. Enables
                indirect injection analysis for those values.
            **kwargs: Additional arguments forwarded to ``Crew.kickoff``.

        Returns:
            The crew output after output scanning.

        Raises:
            CrewAISecurityError: If inputs or outputs violate security policy.
        """
        segments = self._adapter.build_untrusted_segments(inputs, untrusted_keys)
        input_result = self._adapter.scan_text(
            self._adapter.extract_text(inputs),
            "inputs",
            context_segments=segments,
        )
        self._adapter.publish_scan_events_sync(input_result)
        self._adapter.raise_if_blocked(input_result)
        output = self._crew_ref.kickoff(inputs=inputs, **kwargs)
        out_result = self._adapter.scan_text(self._adapter.extract_text(output), "output")
        self._adapter.publish_scan_events_sync(out_result)
        self._adapter.raise_if_blocked(out_result)
        return output

    async def akickoff(
        self,
        inputs: dict[str, Any] | None = None,
        untrusted_keys: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Run a security-scanned asynchronous crew kickoff.

        Args:
            inputs: Kickoff inputs scanned before execution.
            untrusted_keys: Optional untrusted input keys (see :meth:`kickoff`).
            **kwargs: Additional arguments forwarded to ``Crew.akickoff``.

        Returns:
            The crew output after output scanning.

        Raises:
            CrewAISecurityError: If inputs or outputs violate security policy.
        """
        segments = self._adapter.build_untrusted_segments(inputs, untrusted_keys)
        await self._adapter.async_scan_inputs(inputs, context_segments=segments)
        result = await self._crew_ref.akickoff(inputs=inputs, **kwargs)
        await self._adapter.async_check_output(result)
        return result

    async def kickoff_async(
        self,
        inputs: dict[str, Any] | None = None,
        untrusted_keys: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Run a security-scanned ``kickoff_async`` call.

        Args:
            inputs: Kickoff inputs scanned before execution.
            untrusted_keys: Optional untrusted input keys (see :meth:`kickoff`).
            **kwargs: Additional arguments forwarded to ``Crew.kickoff_async``.

        Returns:
            The crew output after output scanning.

        Raises:
            CrewAISecurityError: If inputs or outputs violate security policy.
        """
        segments = self._adapter.build_untrusted_segments(inputs, untrusted_keys)
        await self._adapter.async_scan_inputs(inputs, context_segments=segments)
        result = await self._crew_ref.kickoff_async(inputs=inputs, **kwargs)
        await self._adapter.async_check_output(result)
        return result

    def kickoff_for_each(
        self,
        inputs: list[dict[str, Any]],
        untrusted_keys: Any = None,
        **kwargs: Any,
    ) -> list[Any]:
        """Run security-scanned kickoffs for a batch of inputs.

        Args:
            inputs: List of input dictionaries; each is scanned individually.
            untrusted_keys: Optional untrusted input keys (see :meth:`kickoff`).
            **kwargs: Additional arguments forwarded to ``Crew.kickoff_for_each``.

        Returns:
            List of crew outputs after per-output scanning.

        Raises:
            CrewAISecurityError: If any input or output violates policy.
        """
        for item in inputs:
            segments = self._adapter.build_untrusted_segments(item, untrusted_keys)
            item_result = self._adapter.scan_text(
                self._adapter.extract_text(item),
                "inputs",
                context_segments=segments,
            )
            self._adapter.publish_scan_events_sync(item_result)
            self._adapter.raise_if_blocked(item_result)
        results: list[Any] = list(self._crew_ref.kickoff_for_each(inputs=inputs, **kwargs))
        for result in results:
            out_result = self._adapter.scan_text(self._adapter.extract_text(result), "output")
            self._adapter.publish_scan_events_sync(out_result)
            self._adapter.raise_if_blocked(out_result)
        return results

    async def akickoff_for_each(
        self,
        inputs: list[dict[str, Any]],
        untrusted_keys: Any = None,
        **kwargs: Any,
    ) -> list[Any]:
        """Run security-scanned async kickoffs for a batch of inputs.

        Args:
            inputs: List of input dictionaries; each is scanned individually.
            untrusted_keys: Optional untrusted input keys (see :meth:`kickoff`).
            **kwargs: Additional arguments forwarded to ``Crew.akickoff_for_each``.

        Returns:
            List of crew outputs after per-output scanning.

        Raises:
            CrewAISecurityError: If any input or output violates policy.
        """
        for item in inputs:
            segments = self._adapter.build_untrusted_segments(item, untrusted_keys)
            await self._adapter.async_scan_inputs(item, context_segments=segments)
        results: list[Any] = list(await self._crew_ref.akickoff_for_each(inputs=inputs, **kwargs))
        for result in results:
            await self._adapter.async_check_output(result)
        return results

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to the wrapped crew."""
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._crew_ref, name)


class CrewAIAdapter(Adapter):
    """Adapter for CrewAI framework integration.

    Provides security scanning for CrewAI crews, agents, tasks,
    kickoff inputs/outputs, messages, task guardrails, and tools using
    the existing Q-Guardian security pipeline.
    """

    def __init__(
        self,
        guardian: Guardian | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the CrewAI adapter.

        Args:
            guardian: Optional Guardian instance. When provided, its event
                bus is used for threat events unless overridden in config.
            config: Optional configuration dictionary. Supported keys:
                'event_bus' (EventBus), 'publish_events' (bool).

        Raises:
            RuntimeError: If the CrewAI package is not installed.
        """
        if not CREWAI_AVAILABLE:
            raise RuntimeError(
                "CrewAI is not installed. Install with: pip install 'q-guardian[crewai]'"
            )

        cfg = config or {}
        self._guardian = guardian
        self._config: dict[str, Any] = cfg
        self._context: FrameworkContext | None = None
        self._crew: SecuredCrewProxy | None = None
        self._pending_tasks: set[asyncio.Task[Any]] = set()
        self._event_bus: EventBus | None = cfg.get("event_bus")
        if self._event_bus is None and guardian is not None:
            self._event_bus = getattr(guardian, "event_bus", None)
        self._indirect_config = _resolve_indirect_config(cfg.get("indirect_config"))
        # Output monitoring (P3-3): opt-in via 'output_monitoring' flag;
        # tuning via optional 'output_config' dict/config instance.
        self._output_config = _resolve_output_config(cfg.get("output_config"))
        self._output_monitoring: bool = bool(cfg.get("output_monitoring", False))

    @property
    def name(self) -> str:
        return "crewai"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def framework_name(self) -> str:
        return "CrewAI"

    async def initialize(self, context: FrameworkContext) -> None:
        """Initialize the adapter with framework context.

        Args:
            context: The shared framework context.
        """
        self._context = context
        if self._event_bus is None:
            self._event_bus = getattr(context, "event_bus", None)
        logger.info("CrewAI adapter initialized")

    async def shutdown(self) -> None:
        """Shut down the adapter and release resources."""
        self._crew = None
        self._pending_tasks.clear()
        logger.info("CrewAI adapter shut down")

    async def connect_agent(self, agent_config: dict[str, Any]) -> SecuredCrewProxy:
        """Connect a CrewAI crew to the security framework.

        Args:
            agent_config: Configuration for the agent connection. Supported
                keys: 'crew' (pre-built Crew) or 'agents' + 'tasks' used to
                build one via :meth:`create_crew`, plus optional
                'process'/'crew_kwargs' passed through to ``create_crew``.

        Returns:
            A secured crew proxy wrapping the crew.

        Raises:
            ValueError: If neither a crew nor agents/tasks are provided.
        """
        crew = agent_config.get("crew")
        if crew is None:
            agents = agent_config.get("agents")
            tasks = agent_config.get("tasks")
            if not agents or not tasks:
                raise ValueError("agent_config must contain 'crew' or both 'agents' and 'tasks'")
            crew = self.create_crew(
                agents,
                tasks,
                process=agent_config.get("process"),
                **agent_config.get("crew_kwargs", {}),
            )
        secured = self.secure_crew(crew)
        self._crew = secured
        logger.info("CrewAI crew connected through security proxy")
        return secured

    async def process_prompt(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        """Process a prompt through the full security pipeline.

        Args:
            prompt: The prompt text to process.
            context: Additional processing context.

        Returns:
            Prompt analysis dictionary with decision fields.
        """
        analysis = self.analyze_prompt(prompt)
        analysis_dict: dict[str, Any] = analysis.model_dump()
        await self.publish_analysis_events(analysis_dict, source="prompt")
        return analysis_dict

    async def handle_response(self, response: Any) -> dict[str, Any]:
        """Handle a response from the AI framework.

        Args:
            response: Raw response from CrewAI (CrewOutput, TaskOutput,
                string, dict, or any object with text content).

        Returns:
            Scan result dictionary with decision fields.
        """
        text_content = self.extract_text(response)
        result = self.scan_text(text_content, "response")
        await self.publish_scan_events(result)
        return result

    async def extract_features(self, data: Any) -> dict[str, Any]:
        """Extract security-relevant features from framework data.

        Args:
            data: Raw data from the AI framework.

        Returns:
            Extracted features dictionary including encoding candidates
            and homoglyph detection summaries.
        """
        text_content = self.extract_text(data)
        if not text_content:
            return {}

        features: dict[str, Any] = {
            "length": len(text_content),
            "word_count": len(text_content.split()),
            "line_count": text_content.count("\n") + 1,
        }

        encoding_candidates = detect_all_encodings(text_content)
        features["encoding_candidates"] = [
            {
                "encoding": c.encoding,
                "confidence": c.confidence,
                "decoded_preview": c.metadata.get("decoded_preview", "")[:200],
            }
            for c in encoding_candidates
        ]

        from q_guardian.security.homoglyph import analyze_homoglyphs

        homoglyph_results = analyze_homoglyphs(text_content)
        features["homoglyph"] = {
            "has_confusables": homoglyph_results["has_confusables"],
            "has_mixed_script": homoglyph_results["has_mixed_script"],
            "confusables_count": len(homoglyph_results["confusables"]),
            "mixed_script_count": len(homoglyph_results["mixed_script"]),
        }
        return features

    # ============================================================
    # CrewAI-specific APIs
    # ============================================================

    def create_crew(
        self,
        agents: list[Any],
        tasks: list[Any],
        process: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Build a CrewAI Crew with optional process configuration.

        Args:
            agents: List of CrewAI Agent instances.
            tasks: List of CrewAI Task instances.
            process: Optional CrewAI Process enum value. Defaults to
                sequential when not provided.
            **kwargs: Additional keyword arguments forwarded to ``Crew``.

        Returns:
            A configured CrewAI Crew instance.
        """
        if not CREWAI_AVAILABLE:
            raise RuntimeError("CrewAI is not installed")
        if process is None:
            process = Process.sequential
        return Crew(agents=agents, tasks=tasks, process=process, **kwargs)

    def secure_crew(self, crew: Any) -> SecuredCrewProxy:
        """Wrap a Crew with security-scanned kickoff methods.

        Args:
            crew: The CrewAI Crew instance to secure.

        Returns:
            A proxy exposing scanned kickoff/kickoff_for_each variants.
        """
        return SecuredCrewProxy(crew=crew, adapter=self)

    def scan_inputs(
        self,
        inputs: dict[str, Any] | None,
        context_segments: list[ContentSegment] | None = None,
    ) -> dict[str, Any]:
        """Scan kickoff inputs synchronously and block on violations.

        Args:
            inputs: Kickoff inputs dictionary.
            context_segments: Optional untrusted content segments enabling
                indirect injection analysis.

        Returns:
            Scan result dictionary.

        Raises:
            CrewAISecurityError: If the decision is BLOCK.
        """
        result = self.scan_text(
            self.extract_text(inputs), "inputs", context_segments=context_segments
        )
        self.raise_if_blocked(result)
        return result

    async def async_scan_inputs(
        self,
        inputs: dict[str, Any] | None,
        context_segments: list[ContentSegment] | None = None,
    ) -> dict[str, Any]:
        """Scan kickoff inputs asynchronously and block on violations.

        Args:
            inputs: Kickoff inputs dictionary.
            context_segments: Optional untrusted content segments enabling
                indirect injection analysis.

        Returns:
            Scan result dictionary.

        Raises:
            CrewAISecurityError: If the decision is BLOCK.
        """
        result = self.scan_text(
            self.extract_text(inputs), "inputs", context_segments=context_segments
        )
        await self.publish_scan_events(result)
        self.raise_if_blocked(result)
        return result

    def check_output(self, output: Any) -> dict[str, Any]:
        """Scan a crew/task output synchronously and block on violations.

        Args:
            output: CrewOutput, TaskOutput, or arbitrary response data.

        Returns:
            Scan result dictionary.

        Raises:
            CrewAISecurityError: If the decision is BLOCK.
        """
        result = self.scan_text(self.extract_text(output), "output")
        self.raise_if_blocked(result)
        return result

    async def async_check_output(self, output: Any) -> dict[str, Any]:
        """Scan a crew/task output asynchronously and block on violations.

        Args:
            output: CrewOutput, TaskOutput, or arbitrary response data.

        Returns:
            Scan result dictionary.

        Raises:
            CrewAISecurityError: If the decision is BLOCK.
        """
        result = self.scan_text(self.extract_text(output), "output")
        await self.publish_scan_events(result)
        self.raise_if_blocked(result)
        return result

    def create_task_guardrail(self) -> Callable[[Any], tuple[bool, Any]]:
        """Create a CrewAI task guardrail backed by the security pipeline.

        The returned callable matches CrewAI's guardrail contract:
        ``(TaskOutput) -> tuple[bool, Any]``.

        Returns:
            Guardrail callable returning ``(True, output)`` when safe and
            ``(False, refusal_message)`` when blocked.
        """
        adapter = self

        def guardrail(output: Any) -> tuple[bool, Any]:
            result = adapter.scan_text(adapter.extract_text(output), "task_output")
            adapter.publish_scan_events_sync(result)
            if result.get("decision") == "block":
                refusal = (
                    f"{_BLOCKED_MESSAGE}: risk_score="
                    f"{result.get('risk_score', 0.0)}, "
                    f"findings={len(result.get('findings', []))}"
                )
                return False, refusal
            return True, output

        return guardrail

    def secure_tool(self, tool: Any) -> Any:
        """Wrap a tool so its inputs and outputs pass through scanning.

        Args:
            tool: A CrewAI BaseTool instance or an async/sync callable.

        Returns:
            A secured tool of the same callable shape.

        Raises:
            TypeError: If the tool is neither a BaseTool nor callable.
        """
        if CREWAI_AVAILABLE and isinstance(tool, BaseTool):
            return self._secure_base_tool(tool)
        if callable(tool):
            return self._secure_callable_tool(tool)
        msg = f"Cannot secure tool of unsupported type: {type(tool).__name__}"
        raise TypeError(msg)

    def _secure_base_tool(self, tool: Any) -> Any:
        """Build a BaseTool subclass proxy that scans before delegation."""
        adapter = self
        tool_name = getattr(tool, "name", "tool")
        tool_description = getattr(tool, "description", "")

        def _run_scanned(self: Any, **kwargs: Any) -> Any:
            scan_payload = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            result = adapter.scan_text(scan_payload, "tool_input")
            adapter.publish_scan_events_sync(result)
            adapter.raise_if_blocked(result)
            delegate_result = tool.run(**kwargs)
            out_text = adapter.extract_text(delegate_result)
            out_scan = adapter.scan_text(
                out_text,
                "tool_output",
                context_segments=adapter._tool_output_segments(out_text, str(tool_name)),
            )
            adapter.publish_scan_events_sync(out_scan)
            adapter.raise_if_blocked(out_scan)
            return delegate_result

        secured_class = type(
            f"Secured_{tool_name}",
            (BaseTool,),
            {
                "__annotations__": {"name": str, "description": str},
                "name": f"secured_{tool_name}",
                "description": f"Q-Guardian secured wrapper: {tool_description}",
                "_run": _run_scanned,
            },
        )
        return secured_class()

    def _secure_callable_tool(self, tool: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a plain callable tool with input/output scanning."""
        adapter = self

        @functools.wraps(tool)
        def secured_sync(*args: Any, **kwargs: Any) -> Any:
            scan_payload = ", ".join(str(a) for a in args)
            scan_payload += ", " + ", ".join(f"{k}={v}" for k, v in kwargs.items())
            result = adapter.scan_text(scan_payload, "tool_input")
            adapter.publish_scan_events_sync(result)
            adapter.raise_if_blocked(result)
            delegate_result = tool(*args, **kwargs)
            out_text = adapter.extract_text(delegate_result)
            out_scan = adapter.scan_text(
                out_text,
                "tool_output",
                context_segments=adapter._tool_output_segments(
                    out_text, getattr(tool, "__name__", "callable_tool")
                ),
            )
            adapter.publish_scan_events_sync(out_scan)
            adapter.raise_if_blocked(out_scan)
            return delegate_result

        @functools.wraps(tool)
        async def secured_async(*args: Any, **kwargs: Any) -> Any:
            scan_payload = ", ".join(str(a) for a in args)
            scan_payload += ", " + ", ".join(f"{k}={v}" for k, v in kwargs.items())
            result = adapter.scan_text(scan_payload, "tool_input")
            await adapter.publish_scan_events(result)
            adapter.raise_if_blocked(result)
            delegate_result = await tool(*args, **kwargs)
            out_text = adapter.extract_text(delegate_result)
            out_scan = adapter.scan_text(
                out_text,
                "tool_output",
                context_segments=adapter._tool_output_segments(
                    out_text, getattr(tool, "__name__", "callable_tool")
                ),
            )
            await adapter.publish_scan_events(out_scan)
            adapter.raise_if_blocked(out_scan)
            return delegate_result

        if asyncio.iscoroutinefunction(tool):
            return secured_async
        return secured_sync

    # ============================================================
    # Internal Implementation
    # ============================================================

    def raise_if_blocked(self, result: dict[str, Any]) -> None:
        """Raise a security error when the scan decision is BLOCK.

        Args:
            result: Scan result dictionary produced by :meth:`scan_text`.

        Raises:
            CrewAISecurityError: When the decision is BLOCK.
        """
        if result.get("decision") == "block":
            raise CrewAISecurityError(
                f"{_BLOCKED_MESSAGE}: {result.get('source', 'unknown')}",
                result.get("findings", []),
            )

    def _tool_output_segments(self, output_text: str, tool_name: str) -> list[ContentSegment]:
        """Return a provenance segment for tool output when opted in.

        Enabled via ``config={'tool_output_untrusted': True}``; disabled by
        default so legacy scanning behavior is fully preserved.
        """
        if not self._config.get("tool_output_untrusted", False):
            return []
        if not output_text or not output_text.strip():
            return []
        return [
            ContentSegment(
                content=output_text,
                source_type=SourceType.TOOL_OUTPUT,
                source_id=tool_name,
                position=0,
            )
        ]

    def analyze_prompt(self, prompt: str) -> Any:
        """Run the full prompt pipeline (normalize → validate → rules → decide).

        Args:
            prompt: The prompt text to analyze.

        Returns:
            A PromptAnalysis with findings and decision populated.
        """
        from q_guardian.security.decision import SecurityDecisionEngine
        from q_guardian.security.models import PromptAnalysis
        from q_guardian.security.pipeline import (
            PromptFeatureExtractor,
            PromptNormalizer,
            PromptValidator,
            RuleEngine,
        )

        normalizer = PromptNormalizer()
        validator = PromptValidator()

        normalized = normalizer.normalize(prompt)
        validation_status, validation_errors = validator.validate(normalized)

        feature_extractor = PromptFeatureExtractor()
        features = feature_extractor.extract(normalized)

        engine = RuleEngine()
        findings = engine.analyze(normalized, features)

        analysis = PromptAnalysis(
            original_prompt=prompt,
            normalized_prompt=normalized,
            is_valid=(validation_status.value == "valid"),
            validation_status=validation_status,
            validation_errors=validation_errors,
            features=features,
            findings=findings,
        )

        decision_engine = SecurityDecisionEngine()
        decision_engine.decide(analysis)
        return analysis

    def build_untrusted_segments(
        self,
        inputs: dict[str, Any] | None,
        untrusted_keys: Any = None,
    ) -> list[ContentSegment]:
        """Build content segments from kickoff inputs flagged as untrusted.

        Args:
            inputs: Kickoff inputs dictionary.
            untrusted_keys: Either a list of key names or a mapping of key
                name to ``SourceType`` value. Keys absent from ``inputs``
                are ignored; non-string values are stringified.

        Returns:
            Content segments (possibly empty) with declared provenance.
        """
        if not inputs or untrusted_keys is None:
            return []
        if isinstance(untrusted_keys, dict):
            key_sources: dict[str, str] = {
                str(key): str(value) for key, value in untrusted_keys.items()
            }
        else:
            key_sources = {str(key): SourceType.RAG_CONTEXT.value for key in untrusted_keys}

        segments: list[ContentSegment] = []
        for key, source_type in key_sources.items():
            if key not in inputs:
                continue
            value = inputs[key]
            if value is None:
                continue
            text = value if isinstance(value, str) else self.extract_text(value)
            if not text.strip():
                continue
            try:
                resolved_source = SourceType(source_type)
            except ValueError:
                resolved_source = SourceType.RAG_CONTEXT
            segments.append(
                ContentSegment(
                    content=text,
                    source_type=resolved_source,
                    source_id=key,
                    position=len(segments),
                )
            )
        return segments

    def scan_text(
        self,
        text: str,
        source: str,
        context_segments: list[ContentSegment] | None = None,
        *,
        output_monitoring: bool | None = None,
    ) -> dict[str, Any]:
        """Scan text content using the existing security pipeline.

        Combines rule-based analysis with homoglyph detection (P1-1) and
        encoding detection (P1-2), then applies the existing decision
        architecture (ALLOW/WARN/REVIEW/BLOCK). When untrusted context
        segments are supplied, indirect injection analysis (P3-5) runs on
        them in addition to the direct rules. With output monitoring
        enabled (P3-3), the direction-gated ``om-*`` rules run instead of
        the ``ii-*`` rules and the output is analyzed for leakage.

        Args:
            text: The text content to scan.
            source: Label describing where the text came from.
            context_segments: Optional untrusted content segments enabling
                indirect injection analysis (or om-007 correlation when
                output monitoring is active).
            output_monitoring: Force output monitoring on/off for this
                scan; defaults to the adapter-level flag, which itself
                applies only to output-source labels (inputs keep
                prompt-direction behavior).

        Returns:
            Dictionary with decision, risk_score, findings, source, and
            encoding_context keys.
        """
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
            return {"decision": "allow", "risk_score": 0.0, "findings": [], "source": source}

        if output_monitoring is not None:
            effective_output = bool(output_monitoring)
        else:
            effective_output = self._output_monitoring and source.lower() in _OUTPUT_SOURCE_LABELS

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

        indirect_context: dict[str, Any] | None = None
        if effective_output:
            from q_guardian.output.monitor import build_output_context

            if self._output_config.enabled:
                features.metadata["output_context"] = build_output_context(
                    normalized,
                    source,
                    self._output_config,
                    context_segments=context_segments,
                )
        elif context_segments and self._indirect_config.enabled:
            indirect_context = build_untrusted_context(context_segments, self._indirect_config)
            features.metadata["untrusted_context"] = indirect_context

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

        decision_engine = SecurityDecisionEngine()
        decision_engine.decide(analysis)

        return {
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
            **(
                {
                    "indirect_context": {
                        "segments_scanned": len(indirect_context.get("segments", [])),
                        "segments_omitted": indirect_context.get("segments_omitted", 0),
                        "trusted_count": indirect_context.get("trusted_count", 0),
                        "indirect_findings_count": sum(
                            1 for f in analysis.findings if f.rule_id.startswith("ii-")
                        ),
                    }
                }
                if indirect_context is not None
                else {}
            ),
            **(
                {
                    "output_context": {
                        "source_label": source,
                        "output_findings_count": sum(
                            1 for f in analysis.findings if f.rule_id.startswith("om-")
                        ),
                    }
                }
                if features.metadata.get("output_context") is not None
                else {}
            ),
        }

    def extract_text(self, data: Any) -> str:
        """Extract scannable text from arbitrary CrewAI/framework data.

        Handles strings, dictionaries, lists, CrewOutput/TaskOutput-like
        objects (via their ``raw`` attribute), message-like objects (via
        their ``content`` attribute), and nested structures.

        Args:
            data: Arbitrary data from the CrewAI framework.

        Returns:
            Extracted text content (may be empty).
        """
        if data is None:
            return ""
        if isinstance(data, str):
            return data
        if isinstance(data, bool):
            return str(data)
        if isinstance(data, (int, float)):
            return str(data)
        if isinstance(data, dict):
            parts = [f"{k}: {self.extract_text(v)}" for k, v in data.items()]
            return "\n".join(p for p in parts if p.strip())
        if isinstance(data, (list, tuple, set)):
            return "\n".join(p for p in (self.extract_text(i) for i in data) if p.strip())
        raw_attr = getattr(data, "raw", None)
        if isinstance(raw_attr, str):
            return raw_attr
        content_attr = getattr(data, "content", None)
        if isinstance(content_attr, str):
            return content_attr
        if isinstance(content_attr, list):
            parts = []
            for item in content_attr:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        text_attr = getattr(data, "text", None)
        if isinstance(text_attr, str):
            return text_attr
        return str(data)

    async def publish_analysis_events(self, analysis_dict: dict[str, Any], source: str) -> None:
        """Publish ThreatDetected events for non-allow analyses.

        Args:
            analysis_dict: Serialized PromptAnalysis dictionary.
            source: Label describing the analysis origin.
        """
        await self.publish_scan_events(
            {
                "decision": analysis_dict.get("decision", "allow"),
                "risk_score": analysis_dict.get("risk_score", 0.0),
                "findings": analysis_dict.get("findings", []),
                "source": source,
            }
        )

    async def publish_scan_events(self, result: dict[str, Any]) -> None:
        """Publish a ThreatDetected event when threats are found.

        Args:
            result: Scan result dictionary produced by :meth:`scan_text`.
        """
        if self._event_bus is None:
            return
        if not self._config.get("publish_events", True):
            return
        if result.get("decision", "allow") == "allow":
            return

        from q_guardian.events.standard import ThreatDetected

        await self._event_bus.publish(
            ThreatDetected(
                source=self.name,
                data={
                    "framework": self.framework_name,
                    "decision": result.get("decision"),
                    "risk_score": result.get("risk_score", 0.0),
                    "finding_count": len(result.get("findings", [])),
                    "source": result.get("source", "unknown"),
                    "findings": result.get("findings", []),
                },
            )
        )

    def publish_scan_events_sync(self, result: dict[str, Any]) -> None:
        """Publish threat events from synchronous contexts.

        Safe to call both inside and outside a running event loop. Inside
        a loop, publishing is scheduled as a pending background task.

        Args:
            result: Scan result dictionary produced by :meth:`scan_text`.
        """
        if self._event_bus is None:
            return
        if not self._config.get("publish_events", True):
            return
        if result.get("decision", "allow") == "allow":
            return

        from q_guardian.events.standard import ThreatDetected

        event = ThreatDetected(
            source=self.name,
            data={
                "framework": self.framework_name,
                "decision": result.get("decision"),
                "risk_score": result.get("risk_score", 0.0),
                "finding_count": len(result.get("findings", [])),
                "source": result.get("source", "unknown"),
                "findings": result.get("findings", []),
            },
        )
        coro = self._event_bus.publish(event)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
        else:
            task = loop.create_task(coro)
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)

    def health(self) -> dict[str, Any]:
        """Return adapter health status.

        Returns:
            Dictionary with health status details.
        """
        return {
            "status": "healthy",
            "adapter": self.name,
            "version": self.version,
            "framework": self.framework_name,
            "crewai_available": CREWAI_AVAILABLE,
            "secured_crew_ready": self._crew is not None,
        }

    def configuration(self) -> dict[str, Any]:
        """Return adapter configuration summary.

        Returns:
            Dictionary describing current adapter configuration.
        """
        return {
            "publish_events": self._config.get("publish_events", True),
            "event_bus_connected": self._event_bus is not None,
            "guardian_attached": self._guardian is not None,
            "indirect_injection_enabled": self._indirect_config.enabled,
            "tool_output_untrusted": self._config.get("tool_output_untrusted", False),
        }


def create_crewai_adapter(
    guardian: Guardian | None = None,
    config: dict[str, Any] | None = None,
) -> CrewAIAdapter:
    """Factory function to create a CrewAI adapter.

    Args:
        guardian: Optional Guardian instance for security scanning.
        config: Optional configuration dictionary.

    Returns:
        Configured CrewAIAdapter instance.
    """
    return CrewAIAdapter(guardian=guardian, config=config)
