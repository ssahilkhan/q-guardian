"""Timeline — builds chronological timelines of security events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from q_guardian.response.data import Timeline, TimelineEvent
from q_guardian.response.enums import TimelineFormat
from q_guardian.response.exceptions import EvidenceError

logger = structlog.get_logger(__name__)


class EvidenceTimeline:
    """Builds and queries timelines of events."""

    def __init__(self) -> None:
        self._timelines: dict[str, Timeline] = {}

    def create_timeline(
        self,
        timeline_id: str,
        correlation_id: str = "",
        description: str = "",
    ) -> Timeline:
        """Create a new timeline."""
        timeline = Timeline(
            correlation_id=correlation_id,
            timeline_id=timeline_id,
            description=description,
        )
        self._timelines[timeline_id] = timeline
        return timeline

    def add_event(
        self,
        timeline_id: str,
        event_type: str,
        source: str,
        data: dict[str, Any] | None = None,
        severity: str = "info",
        timestamp: datetime | None = None,
    ) -> TimelineEvent:
        """Add an event to a timeline."""
        timeline = self._timelines.get(timeline_id)
        if timeline is None:
            raise EvidenceError(f"Timeline not found: {timeline_id}")

        event = TimelineEvent(
            event_type=event_type,
            source=source,
            data=data or {},
            severity=severity,
        )
        if timestamp:
            event.timestamp = timestamp

        timeline.events.append(event)
        return event

    def get_timeline(self, timeline_id: str) -> Timeline | None:
        return self._timelines.get(timeline_id)

    def get_events(
        self,
        timeline_id: str,
        event_type: str | None = None,
        min_severity: str | None = None,
    ) -> list[TimelineEvent]:
        """Get events from a timeline with optional filtering."""
        timeline = self._timelines.get(timeline_id)
        if timeline is None:
            return []

        events = list(timeline.events)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if min_severity:
            severity_order = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}
            min_val = severity_order.get(min_severity, 0)
            events = [e for e in events if severity_order.get(e.severity, 0) >= min_val]

        return sorted(events, key=lambda e: e.timestamp)

    def export_timeline(
        self,
        timeline_id: str,
        format_type: TimelineFormat = TimelineFormat.JSON,
    ) -> str:
        """Export a timeline in the given format."""
        timeline = self._timelines.get(timeline_id)
        if timeline is None:
            raise EvidenceError(f"Timeline not found: {timeline_id}")

        if format_type == TimelineFormat.JSON:
            return self._export_json(timeline)
        elif format_type == TimelineFormat.MARKDOWN:
            return self._export_text(timeline)
        elif format_type == TimelineFormat.CSV:
            return self._export_csv(timeline)
        else:
            raise EvidenceError(f"Unsupported format: {format_type}")

    def list_timelines(self) -> list[Timeline]:
        return list(self._timelines.values())

    @staticmethod
    def _export_json(timeline: Timeline) -> str:
        import json
        events_data = []
        for e in sorted(timeline.events, key=lambda x: x.timestamp):
            events_data.append({
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "source": e.source,
                "severity": e.severity,
                "data": e.data,
            })
        return json.dumps({"timeline_id": timeline.timeline_id, "events": events_data}, indent=2)

    @staticmethod
    def _export_text(timeline: Timeline) -> str:
        lines: list[str] = []
        for e in sorted(timeline.events, key=lambda x: x.timestamp):
            lines.append(
                f"[{e.timestamp.isoformat()}] [{e.severity.upper()}] "
                f"{e.event_type} | {e.source}"
            )
        return "\n".join(lines)

    @staticmethod
    def _export_csv(timeline: Timeline) -> str:
        lines = ["timestamp,event_type,source,severity"]
        for e in sorted(timeline.events, key=lambda x: x.timestamp):
            lines.append(
                f"{e.timestamp.isoformat()},{e.event_type},{e.source},{e.severity}"
            )
        return "\n".join(lines)
