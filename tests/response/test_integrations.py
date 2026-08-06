"""Tests for Integrations subsystem."""

from q_guardian.response.enums import IntegrationType
from q_guardian.response.integrations.cortex import CortexIntegration
from q_guardian.response.integrations.qradar import QRadarIntegration
from q_guardian.response.integrations.sentinel import SentinelIntegration
from q_guardian.response.integrations.servicenow import ServiceNowIntegration
from q_guardian.response.integrations.splunk import SplunkIntegration


class TestSentinelIntegration:
    def test_send_incident(self) -> None:
        s = SentinelIntegration()
        r = s.send_incident("Test", "High", description="desc")
        assert r.success is True or r.response_data is not None
        assert r.integration_type == IntegrationType.SENTINEL

    def test_send_alert(self) -> None:
        s = SentinelIntegration()
        r = s.send_alert("Alert1", "Medium")
        assert r.integration_type == IntegrationType.SENTINEL

    def test_get_results(self) -> None:
        s = SentinelIntegration()
        s.send_incident("a", "Low")
        s.send_alert("b", "High")
        assert len(s.get_results()) == 2


class TestSplunkIntegration:
    def test_send_event(self) -> None:
        s = SplunkIntegration()
        r = s.send_event("src", "type", {"key": "val"})
        assert r.integration_type == IntegrationType.SPLUNK

    def test_send_alert(self) -> None:
        s = SplunkIntegration()
        r = s.send_alert("Alert", "High", search_query="index=*")
        assert r.integration_type == IntegrationType.SPLUNK

    def test_get_results(self) -> None:
        s = SplunkIntegration()
        s.send_event("src", "type", {})
        assert len(s.get_results()) == 1


class TestQRadarIntegration:
    def test_send_offense(self) -> None:
        q = QRadarIntegration()
        r = q.send_offense("desc", severity=8)
        assert r.integration_type == IntegrationType.QRADAR

    def test_send_event(self) -> None:
        q = QRadarIntegration()
        r = q.send_event("event1", payload={"data": 1})
        assert r.integration_type == IntegrationType.QRADAR

    def test_get_results(self) -> None:
        q = QRadarIntegration()
        q.send_offense("d", 5)
        assert len(q.get_results()) == 1


class TestCortexIntegration:
    def test_create_case(self) -> None:
        c = CortexIntegration()
        r = c.create_case("Case1", severity=3, description="desc")
        assert r.integration_type == IntegrationType.CORTEX_XSOAR

    def test_run_analyzer(self) -> None:
        c = CortexIntegration()
        r = c.run_analyzer("analyzer1", "ip", "1.2.3.4")
        assert r.integration_type == IntegrationType.CORTEX_XSOAR

    def test_get_results(self) -> None:
        c = CortexIntegration()
        c.create_case("c", 1)
        assert len(c.get_results()) == 1


class TestServiceNowIntegration:
    def test_create_incident(self) -> None:
        s = ServiceNowIntegration()
        r = s.create_incident("Incident1", urgency="high")
        assert r.integration_type == IntegrationType.SERVICENOW

    def test_create_change_request(self) -> None:
        s = ServiceNowIntegration()
        r = s.create_change_request("Change1", risk="medium")
        assert r.integration_type == IntegrationType.SERVICENOW

    def test_get_results(self) -> None:
        s = ServiceNowIntegration()
        s.create_incident("i")
        assert len(s.get_results()) == 1
