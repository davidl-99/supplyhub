import pytest

from app.modules.authorization.permissions import (
    ALL_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
    permissions_for_role,
    role_has_permission,
)
from app.modules.identity.roles import MEMBERSHIP_ROLES, MembershipRole

EXPECTED_ROLE_PERMISSIONS: dict[MembershipRole, frozenset[Permission]] = {
    "organization_admin": ALL_PERMISSIONS,
    "catalog_manager": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PRODUCT_READ,
            Permission.PRODUCT_CREATE,
            Permission.PRODUCT_UPDATE,
            Permission.PRODUCT_DEACTIVATE,
        }
    ),
    "warehouse_operator": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PRODUCT_READ,
            Permission.WAREHOUSE_READ,
            Permission.INVENTORY_READ,
            Permission.INVENTORY_ADJUST,
            Permission.RESERVATION_READ,
            Permission.RESERVATION_CREATE,
            Permission.RESERVATION_RELEASE,
            Permission.RESERVATION_CONSUME,
            Permission.ORDER_READ,
            Permission.ORDER_FULFILL,
        }
    ),
    "buyer": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.ORDER_READ,
            Permission.ORDER_CREATE,
            Permission.ORDER_PLACE,
            Permission.ORDER_CANCEL,
        }
    ),
    "viewer": frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.PRODUCT_READ,
            Permission.WAREHOUSE_READ,
            Permission.INVENTORY_READ,
            Permission.RESERVATION_READ,
            Permission.ORDER_READ,
        }
    ),
}


def test_permission_mapping_covers_every_membership_role() -> None:
    assert set(ROLE_PERMISSIONS) == set(MEMBERSHIP_ROLES)


@pytest.mark.parametrize("role", MEMBERSHIP_ROLES)
def test_role_has_exact_expected_permissions(role: MembershipRole) -> None:
    assert permissions_for_role(role) == EXPECTED_ROLE_PERMISSIONS[role]


def test_organization_admin_has_every_permission() -> None:
    assert permissions_for_role("organization_admin") == ALL_PERMISSIONS


@pytest.mark.parametrize(
    ("role", "permission"),
    [
        ("catalog_manager", Permission.INVENTORY_ADJUST),
        ("warehouse_operator", Permission.MEMBERSHIP_CREATE),
        ("buyer", Permission.ORDER_FULFILL),
        ("viewer", Permission.PRODUCT_UPDATE),
    ],
)
def test_role_does_not_gain_unrelated_permission(
    role: MembershipRole,
    permission: Permission,
) -> None:
    assert not role_has_permission(role, permission)


def test_unknown_role_has_no_permissions() -> None:
    assert permissions_for_role("unknown_role") == frozenset()
