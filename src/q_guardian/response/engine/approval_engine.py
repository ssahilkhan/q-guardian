"""Approval Engine — automatic, manual, multi-level, timeout, quorum approvals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from q_guardian.response.data import ApprovalRequest
from q_guardian.response.enums import ApprovalStatus, ApprovalType
from q_guardian.response.exceptions import ApprovalError

logger = structlog.get_logger(__name__)


class ApprovalEngine:
    """Manages approval workflows for sensitive actions.

    Supports automatic, manual, multi-level, timeout-based,
    and quorum-based approvals.
    """

    def __init__(self, default_timeout_seconds: float = 300.0) -> None:
        self._requests: dict[str, ApprovalRequest] = {}
        self._default_timeout = default_timeout_seconds

    def request_approval(
        self,
        action: str,
        description: str = "",
        approval_type: ApprovalType = ApprovalType.MANUAL,
        approvers: list[str] | None = None,
        required_approvals: int = 1,
        timeout_seconds: float | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str = "",
    ) -> ApprovalRequest:
        """Create an approval request."""
        req = ApprovalRequest(
            correlation_id=correlation_id,
            approval_type=approval_type,
            action=action,
            description=description,
            context=context or {},
            approvers=approvers or [],
            required_approvals=required_approvals,
            timeout_seconds=timeout_seconds or self._default_timeout,
        )
        self._requests[req.request_id] = req

        # Auto-approve if automatic
        if approval_type == ApprovalType.AUTOMATIC:
            self._auto_approve(req)

        logger.info(
            "approval_requested",
            request_id=req.request_id,
            action=action,
            type=approval_type.value,
        )
        return req

    def approve(
        self,
        request_id: str,
        approver: str,
    ) -> ApprovalRequest:
        """Approve a pending request."""
        req = self._get_request(request_id)
        if req.status != ApprovalStatus.PENDING:
            raise ApprovalError(f"Request {request_id} is not pending (status={req.status.value})")

        if approver not in req.approvers:
            req.approvers.append(approver)

        req.approvals_received.append(approver)

        if len(req.approvals_received) >= req.required_approvals:
            req.status = ApprovalStatus.APPROVED
            req.resolved_at = datetime.now(UTC)
            logger.info(
                "approval_granted",
                request_id=request_id,
                approver=approver,
                total=len(req.approvals_received),
            )
        else:
            logger.info(
                "approval_partial",
                request_id=request_id,
                approver=approver,
                current=len(req.approvals_received),
                required=req.required_approvals,
            )

        return req

    def reject(
        self,
        request_id: str,
        approver: str,
        reason: str = "",
    ) -> ApprovalRequest:
        """Reject a pending request."""
        req = self._get_request(request_id)
        req.status = ApprovalStatus.REJECTED
        req.resolved_at = datetime.now(UTC)
        req.metadata["rejection_reason"] = reason
        req.metadata["rejected_by"] = approver
        logger.info(
            "approval_rejected",
            request_id=request_id,
            approver=approver,
            reason=reason,
        )
        return req

    def cancel(self, request_id: str) -> ApprovalRequest:
        """Cancel a pending request."""
        req = self._get_request(request_id)
        req.status = ApprovalStatus.CANCELLED
        req.resolved_at = datetime.now(UTC)
        return req

    def check_timeouts(self) -> list[ApprovalRequest]:
        """Check for timed-out requests and expire them."""
        now = datetime.now(UTC)
        expired: list[ApprovalRequest] = []
        for req in self._requests.values():
            if req.status != ApprovalStatus.PENDING:
                continue
            elapsed = (now - req.created_at).total_seconds()
            if elapsed > req.timeout_seconds:
                req.status = ApprovalStatus.EXPIRED
                req.resolved_at = now
                expired.append(req)
                logger.info("approval_expired", request_id=req.request_id)
        return expired

    def is_approved(self, request_id: str) -> bool:
        req = self._get_request(request_id)
        return req.status == ApprovalStatus.APPROVED

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        return self._requests.get(request_id)

    def list_pending(self) -> list[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status == ApprovalStatus.PENDING]

    def list_all(self) -> list[ApprovalRequest]:
        return list(self._requests.values())

    def _get_request(self, request_id: str) -> ApprovalRequest:
        req = self._requests.get(request_id)
        if req is None:
            raise ApprovalError(f"Approval request not found: {request_id}")
        return req

    def _auto_approve(self, req: ApprovalRequest) -> None:
        req.status = ApprovalStatus.APPROVED
        req.resolved_at = datetime.now(UTC)
        req.approvals_received = ["system"]
        logger.info("approval_auto_granted", request_id=req.request_id)
