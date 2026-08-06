"""Tests for Evidence subsystem."""

import pytest

from q_guardian.response.enums import EvidenceType, TimelineFormat
from q_guardian.response.evidence.collector import EvidenceCollector
from q_guardian.response.evidence.snapshot import EvidenceSnapshot
from q_guardian.response.evidence.timeline import EvidenceTimeline
from q_guardian.response.exceptions import EvidenceError


class TestEvidenceCollector:
    def test_collect(self) -> None:
        c = EvidenceCollector()
        rec = c.collect(EvidenceType.PROMPT, source="test", data={"key": "val"})
        assert rec.evidence_type == EvidenceType.PROMPT

    def test_get(self) -> None:
        c = EvidenceCollector()
        rec = c.collect(EvidenceType.RUNTIME_CONTEXT, source="net")
        assert c.get(rec.evidence_id) is rec

    def test_get_nonexistent(self) -> None:
        c = EvidenceCollector()
        assert c.get("nope") is None

    def test_get_by_correlation(self) -> None:
        c = EvidenceCollector()
        c.collect(EvidenceType.PROMPT, source="a", correlation_id="c1")
        c.collect(EvidenceType.PROMPT, source="b", correlation_id="c1")
        c.collect(EvidenceType.PROMPT, source="c", correlation_id="c2")
        assert len(c.get_by_correlation("c1")) == 2

    def test_get_by_type(self) -> None:
        c = EvidenceCollector()
        c.collect(EvidenceType.PROMPT, source="a")
        c.collect(EvidenceType.RUNTIME_CONTEXT, source="b")
        assert len(c.get_by_type(EvidenceType.PROMPT)) == 1

    def test_count(self) -> None:
        c = EvidenceCollector()
        assert c.count() == 0
        c.collect(EvidenceType.PROMPT, source="a")
        assert c.count() == 1

    def test_clear(self) -> None:
        c = EvidenceCollector()
        c.collect(EvidenceType.PROMPT, source="a")
        c.clear()
        assert c.count() == 0

    def test_list_all(self) -> None:
        c = EvidenceCollector()
        c.collect(EvidenceType.PROMPT, source="a")
        c.collect(EvidenceType.RUNTIME_CONTEXT, source="b")
        assert len(c.list_all()) == 2


class TestEvidenceSnapshot:
    def test_capture(self) -> None:
        collector = EvidenceCollector()
        snap = EvidenceSnapshot(collector)
        result = snap.capture("test-snap", state={"x": 1})
        assert result["name"] == "test-snap"
        assert collector.count() == 1

    def test_get_snapshots(self) -> None:
        collector = EvidenceCollector()
        snap = EvidenceSnapshot(collector)
        snap.capture("s1", state={})
        snap.capture("s2", state={})
        assert len(snap.get_snapshots()) == 2

    def test_get_snapshot_by_name(self) -> None:
        collector = EvidenceCollector()
        snap = EvidenceSnapshot(collector)
        snap.capture("s1", state={"v": 42})
        result = snap.get_snapshot_by_name("s1")
        assert result is not None
        assert result["state"]["v"] == 42

    def test_get_snapshot_by_name_missing(self) -> None:
        collector = EvidenceCollector()
        snap = EvidenceSnapshot(collector)
        assert snap.get_snapshot_by_name("nope") is None


class TestEvidenceTimeline:
    def test_create_timeline(self) -> None:
        tl = EvidenceTimeline()
        timeline = tl.create_timeline("tl-1", description="test timeline")
        assert timeline.timeline_id == "tl-1"

    def test_add_event(self) -> None:
        tl = EvidenceTimeline()
        tl.create_timeline("tl-1")
        event = tl.add_event("tl-1", event_type="alert", source="siem", severity="warning")
        assert event.event_type == "alert"
        assert event.severity == "warning"

    def test_add_event_to_missing_timeline(self) -> None:
        tl = EvidenceTimeline()
        with pytest.raises(EvidenceError, match="not found"):
            tl.add_event("missing", event_type="a", source="b")

    def test_get_events(self) -> None:
        tl = EvidenceTimeline()
        tl.create_timeline("tl-1")
        tl.add_event("tl-1", event_type="alert", source="s1", severity="warning")
        tl.add_event("tl-1", event_type="error", source="s2", severity="critical")
        events = tl.get_events("tl-1")
        assert len(events) == 2

    def test_get_events_filtered_by_type(self) -> None:
        tl = EvidenceTimeline()
        tl.create_timeline("tl-1")
        tl.add_event("tl-1", event_type="alert", source="s1")
        tl.add_event("tl-1", event_type="error", source="s2")
        assert len(tl.get_events("tl-1", event_type="alert")) == 1

    def test_get_events_filtered_by_severity(self) -> None:
        tl = EvidenceTimeline()
        tl.create_timeline("tl-1")
        tl.add_event("tl-1", event_type="a", source="s", severity="info")
        tl.add_event("tl-1", event_type="b", source="s", severity="critical")
        assert len(tl.get_events("tl-1", min_severity="error")) == 1

    def test_export_json(self) -> None:
        tl = EvidenceTimeline()
        tl.create_timeline("tl-1")
        tl.add_event("tl-1", event_type="a", source="s")
        output = tl.export_timeline("tl-1", TimelineFormat.JSON)
        assert "timeline_id" in output

    def test_export_text(self) -> None:
        tl = EvidenceTimeline()
        tl.create_timeline("tl-1")
        tl.add_event("tl-1", event_type="a", source="s", severity="warning")
        output = tl.export_timeline("tl-1", TimelineFormat.MARKDOWN)
        assert "WARNING" in output

    def test_export_csv(self) -> None:
        tl = EvidenceTimeline()
        tl.create_timeline("tl-1")
        tl.add_event("tl-1", event_type="a", source="s")
        output = tl.export_timeline("tl-1", TimelineFormat.CSV)
        assert "timestamp,event_type" in output

    def test_export_missing_timeline(self) -> None:
        tl = EvidenceTimeline()
        with pytest.raises(EvidenceError, match="not found"):
            tl.export_timeline("missing")

    def test_list_timelines(self) -> None:
        tl = EvidenceTimeline()
        tl.create_timeline("t1")
        tl.create_timeline("t2")
        assert len(tl.list_timelines()) == 2
