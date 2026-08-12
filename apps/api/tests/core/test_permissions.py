"""Capability-based permission architecture tests."""

from __future__ import annotations

import pytest

from app.core.permissions.capabilities import StaffCapability
from app.core.permissions.permission_service import PermissionDenied, PermissionService
from app.core.permissions.user_capabilities import default_capabilities_for_role
from app.domain.enums import UserRole, normalize_user_role


def test_normalize_legacy_job_titles_to_staff():
    assert normalize_user_role("manager") == UserRole.STAFF
    assert normalize_user_role("service_advisor") == UserRole.STAFF
    assert normalize_user_role("mechanic") == UserRole.STAFF
    assert normalize_user_role("receptionist") == UserRole.STAFF
    assert normalize_user_role("technician") == UserRole.STAFF
    assert normalize_user_role("owner") == UserRole.OWNER
    assert normalize_user_role("staff") == UserRole.STAFF
    assert normalize_user_role("ai_agent") == UserRole.AI_AGENT


def test_staff_defaults_exclude_calls_and_payments():
    caps = default_capabilities_for_role(UserRole.STAFF)
    assert StaffCapability.CUSTOMER_MANAGEMENT.value in caps
    assert StaffCapability.INSPECTION_INPUT.value in caps
    assert StaffCapability.CUSTOMER_COMMUNICATION.value not in caps
    assert StaffCapability.PAYMENT_HANDLING.value not in caps
    assert len(caps) == len(StaffCapability) - 2


def test_owner_has_all_capabilities():
    svc = PermissionService()
    assert svc.has_capability(
        role=UserRole.OWNER,
        capabilities=[],
        required=StaffCapability.PAYMENT_HANDLING,
    )


def test_staff_capability_gate():
    svc = PermissionService()
    caps = [StaffCapability.CUSTOMER_MANAGEMENT.value]
    assert svc.has_capability(
        role=UserRole.STAFF,
        capabilities=caps,
        required=StaffCapability.CUSTOMER_MANAGEMENT,
    )
    assert not svc.has_capability(
        role=UserRole.STAFF,
        capabilities=caps,
        required=StaffCapability.PAYMENT_HANDLING,
    )
    with pytest.raises(PermissionDenied):
        svc.require(
            role=UserRole.STAFF,
            capabilities=caps,
            required=StaffCapability.PAYMENT_HANDLING,
        )


def test_ai_agent_default_excludes_payment():
    caps = default_capabilities_for_role(UserRole.AI_AGENT)
    assert StaffCapability.CUSTOMER_COMMUNICATION.value in caps
    assert StaffCapability.PAYMENT_HANDLING.value not in caps


def test_membership_caps_override_stale_jwt_subset():
    """Team permission edits write membership caps; auth must prefer those over JWT."""
    svc = PermissionService()
    jwt_caps = [
        StaffCapability.CUSTOMER_MANAGEMENT.value,
        StaffCapability.APPOINTMENT_MANAGEMENT.value,
    ]
    membership_caps = [
        *jwt_caps,
        StaffCapability.PAYMENT_HANDLING.value,
    ]
    resolved = svc.resolve_capabilities(
        role=UserRole.STAFF,
        stored_capabilities=membership_caps,
    )
    assert StaffCapability.PAYMENT_HANDLING.value in resolved
    assert not svc.has_capability(
        role=UserRole.STAFF,
        capabilities=jwt_caps,
        required=StaffCapability.PAYMENT_HANDLING,
    )
    assert svc.has_capability(
        role=UserRole.STAFF,
        capabilities=membership_caps,
        required=StaffCapability.PAYMENT_HANDLING,
    )


def test_role_labels_modern_only():
    from app.domain.enums import ROLE_LABELS

    assert set(ROLE_LABELS.keys()) == {UserRole.OWNER, UserRole.STAFF, UserRole.AI_AGENT}
