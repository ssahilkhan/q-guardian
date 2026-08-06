"""Tests for Response Engine (core)."""

from q_guardian.response.data import ActionPlan, PolicyDecision, ResponseRequest, RiskAssessment
from q_guardian.response.engine.response_engine import ResponseEngine
from q_guardian.response.enums import ResponseAction, ResponseStatus


def _make_request(
    action: str = "block",
    risk_level: str = "high",
    threat_level: str = "none",
    correlation_id: str = "",
) -> ResponseRequest:
    return ResponseRequest(
        correlation_id=correlation_id,
        policy_decision=PolicyDecision(action=action, outcome=action, risk_score=0.8),
        risk_assessment=RiskAssessment(
            risk_score=0.8, risk_level=risk_level, threat_level=threat_level
        ),
    )


class TestResponseEngine:
    def test_process_block(self) -> None:
        engine = ResponseEngine()
        req = _make_request(action="block")
        result = engine.process(req)
        assert result.status == ResponseStatus.COMPLETED
        assert result.action == ResponseAction.BLOCK

    def test_process_quarantine(self) -> None:
        engine = ResponseEngine()
        req = _make_request(action="quarantine")
        result = engine.process(req)
        assert result.status == ResponseStatus.COMPLETED
        assert result.action == ResponseAction.QUARANTINE

    def test_process_escalate(self) -> None:
        engine = ResponseEngine()
        req = _make_request(action="escalate")
        result = engine.process(req)
        assert result.status == ResponseStatus.COMPLETED
        assert result.action == ResponseAction.ESCALATE

    def test_process_from_action_plan(self) -> None:
        engine = ResponseEngine()
        req = ResponseRequest(
            action_plan=ActionPlan(actions=["block"]),
        )
        result = engine.process(req)
        assert result.action == ResponseAction.BLOCK

    def test_process_from_risk_only(self) -> None:
        engine = ResponseEngine()
        req = ResponseRequest(
            risk_assessment=RiskAssessment(risk_level="critical", threat_level="critical"),
        )
        result = engine.process(req)
        assert result.action == ResponseAction.BLOCK

    def test_process_risk_high(self) -> None:
        engine = ResponseEngine()
        req = ResponseRequest(
            risk_assessment=RiskAssessment(risk_level="high"),
        )
        result = engine.process(req)
        assert result.action == ResponseAction.ESCALATE

    def test_process_risk_moderate(self) -> None:
        engine = ResponseEngine()
        req = ResponseRequest(
            risk_assessment=RiskAssessment(risk_level="moderate"),
        )
        result = engine.process(req)
        assert result.action == ResponseAction.WARN

    def test_process_risk_low(self) -> None:
        engine = ResponseEngine()
        req = ResponseRequest(
            risk_assessment=RiskAssessment(risk_level="low"),
        )
        result = engine.process(req)
        assert result.action == ResponseAction.ALLOW

    def test_process_no_inputs(self) -> None:
        engine = ResponseEngine()
        req = ResponseRequest()
        result = engine.process(req)
        assert result.action == ResponseAction.ALLOW

    def test_idempotency(self) -> None:
        engine = ResponseEngine()
        req = _make_request(action="block", correlation_id="idem-1")
        result1 = engine.process(req)
        result2 = engine.process(req)
        assert result1.result_id == result2.result_id

    def test_get_result(self) -> None:
        engine = ResponseEngine()
        req = _make_request(action="block", correlation_id="c1")
        result = engine.process(req)
        assert engine.get_result("c1") is result

    def test_get_result_nonexistent(self) -> None:
        engine = ResponseEngine()
        assert engine.get_result("nope") is None

    def test_get_all_results(self) -> None:
        engine = ResponseEngine()
        engine.process(_make_request(action="block", correlation_id="c1"))
        engine.process(_make_request(action="block", correlation_id="c2"))
        assert len(engine.get_all_results()) == 2

    def test_clear(self) -> None:
        engine = ResponseEngine()
        engine.process(_make_request(action="block", correlation_id="c1"))
        engine.clear()
        assert len(engine.get_all_results()) == 0
