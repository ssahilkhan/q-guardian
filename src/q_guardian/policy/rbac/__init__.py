"""RBAC — Role-Based Access Control for policy operations."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.policy.data import RBACPermission
from q_guardian.policy.enums import Permission
from q_guardian.policy.exceptions import RBACError

logger = structlog.get_logger(__name__)


class RBACManager:
    """Role-Based Access Control for policy operations."""

    def __init__(self, default_role: str = "viewer") -> None:
        self._roles: dict[str, RBACPermission] = {}
        self._user_roles: dict[str, str] = {}  # user_id -> role
        self._default_role = default_role
        self._init_defaults()

    def _init_defaults(self) -> None:
        self._roles["admin"] = RBACPermission(
            role="admin",
            permissions=list(Permission),
        )
        self._roles["editor"] = RBACPermission(
            role="editor",
            permissions=[
                Permission.POLICY_CREATE,
                Permission.POLICY_READ,
                Permission.POLICY_UPDATE,
                Permission.POLICY_EVALUATE,
                Permission.POLICY_ACTIVATE,
                Permission.POLICY_DEACTIVATE,
                Permission.POLICY_SIMULATE,
            ],
        )
        self._roles["viewer"] = RBACPermission(
            role="viewer",
            permissions=[
                Permission.POLICY_READ,
                Permission.POLICY_EVALUATE,
                Permission.POLICY_SIMULATE,
            ],
        )

    def assign_role(self, user_id: str, role: str) -> None:
        if role not in self._roles:
            raise RBACError(f"Unknown role: {role}")
        self._user_roles[user_id] = role
        logger.info("role_assigned", user_id=user_id, role=role)

    def revoke_role(self, user_id: str) -> None:
        self._user_roles.pop(user_id, None)

    def get_role(self, user_id: str) -> str:
        return self._user_roles.get(user_id, self._default_role)

    def check_permission(self, user_id: str, permission: Permission) -> bool:
        role = self.get_role(user_id)
        role_perms = self._roles.get(role)
        if role_perms is None:
            return False
        return permission in role_perms.permissions

    def require_permission(self, user_id: str, permission: Permission) -> None:
        if not self.check_permission(user_id, permission):
            role = self.get_role(user_id)
            raise RBACError(
                f"User '{user_id}' (role={role}) lacks permission: {permission.value}"
            )

    def create_role(
        self,
        role: str,
        permissions: list[Permission],
        policy_ids: list[str] | None = None,
    ) -> None:
        self._roles[role] = RBACPermission(
            role=role,
            permissions=permissions,
            policy_ids=policy_ids or [],
        )
        logger.info("role_created", role=role, permission_count=len(permissions))

    def delete_role(self, role: str) -> bool:
        if role in ("admin", "editor", "viewer"):
            raise RBACError(f"Cannot delete built-in role: {role}")
        return self._roles.pop(role, None) is not None

    def list_roles(self) -> list[str]:
        return list(self._roles.keys())

    def get_role_permissions(self, role: str) -> RBACPermission | None:
        return self._roles.get(role)

    def list_user_roles(self) -> dict[str, str]:
        return dict(self._user_roles)
