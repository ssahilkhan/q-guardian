"""Tests for the RBAC Manager."""

import pytest

from q_guardian.policy.enums import Permission
from q_guardian.policy.exceptions import RBACError
from q_guardian.policy.rbac import RBACManager


class TestRBACManager:
    def test_default_role(self):
        rbac = RBACManager()
        assert rbac.get_role("unknown-user") == "viewer"

    def test_assign_role(self):
        rbac = RBACManager()
        rbac.assign_role("user1", "admin")
        assert rbac.get_role("user1") == "admin"

    def test_assign_unknown_role_raises(self):
        rbac = RBACManager()
        with pytest.raises(RBACError, match="Unknown role"):
            rbac.assign_role("user1", "nonexistent")

    def test_revoke_role(self):
        rbac = RBACManager()
        rbac.assign_role("user1", "admin")
        rbac.revoke_role("user1")
        assert rbac.get_role("user1") == "viewer"  # falls back to default

    def test_admin_permissions(self):
        rbac = RBACManager()
        rbac.assign_role("admin1", "admin")
        assert rbac.check_permission("admin1", Permission.POLICY_CREATE) is True
        assert rbac.check_permission("admin1", Permission.POLICY_DELETE) is True
        assert rbac.check_permission("admin1", Permission.POLICY_ADMIN) is True

    def test_editor_permissions(self):
        rbac = RBACManager()
        rbac.assign_role("editor1", "editor")
        assert rbac.check_permission("editor1", Permission.POLICY_CREATE) is True
        assert rbac.check_permission("editor1", Permission.POLICY_READ) is True
        assert rbac.check_permission("editor1", Permission.POLICY_DELETE) is False

    def test_viewer_permissions(self):
        rbac = RBACManager()
        assert rbac.check_permission("viewer1", Permission.POLICY_READ) is True
        assert rbac.check_permission("viewer1", Permission.POLICY_CREATE) is False
        assert rbac.check_permission("viewer1", Permission.POLICY_DELETE) is False

    def test_require_permission_passes(self):
        rbac = RBACManager()
        rbac.assign_role("user1", "admin")
        rbac.require_permission("user1", Permission.POLICY_CREATE)  # no error

    def test_require_permission_fails(self):
        rbac = RBACManager()
        with pytest.raises(RBACError, match="lacks permission"):
            rbac.require_permission("viewer1", Permission.POLICY_DELETE)

    def test_create_custom_role(self):
        rbac = RBACManager()
        rbac.create_role("custom", [Permission.POLICY_READ])
        assert "custom" in rbac.list_roles()
        rbac.assign_role("user1", "custom")
        assert rbac.check_permission("user1", Permission.POLICY_READ) is True
        assert rbac.check_permission("user1", Permission.POLICY_CREATE) is False

    def test_delete_custom_role(self):
        rbac = RBACManager()
        rbac.create_role("temp", [Permission.POLICY_READ])
        assert rbac.delete_role("temp") is True
        assert "temp" not in rbac.list_roles()

    def test_delete_builtin_role_raises(self):
        rbac = RBACManager()
        with pytest.raises(RBACError, match="Cannot delete built-in"):
            rbac.delete_role("admin")

    def test_list_roles(self):
        rbac = RBACManager()
        roles = rbac.list_roles()
        assert "admin" in roles
        assert "editor" in roles
        assert "viewer" in roles

    def test_get_role_permissions(self):
        rbac = RBACManager()
        perms = rbac.get_role_permissions("admin")
        assert perms is not None
        assert len(perms.permissions) > 0

    def test_get_role_permissions_unknown(self):
        rbac = RBACManager()
        assert rbac.get_role_permissions("nonexistent") is None

    def test_list_user_roles(self):
        rbac = RBACManager()
        rbac.assign_role("u1", "admin")
        rbac.assign_role("u2", "editor")
        roles = rbac.list_user_roles()
        assert roles["u1"] == "admin"
        assert roles["u2"] == "editor"
