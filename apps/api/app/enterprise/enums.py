"""Enterprise enums."""

from __future__ import annotations

from enum import StrEnum


class EnterpriseRole(StrEnum):
    FRANCHISE_OWNER = "franchise_owner"
    ORG_ADMIN = "org_admin"
    REGIONAL_MANAGER = "regional_manager"
    LOCATION_MANAGER = "location_manager"
    LOCATION_STAFF = "location_staff"
    AUDITOR = "auditor"
    API_CLIENT = "api_client"


# Higher number = more privilege
ROLE_RANK: dict[EnterpriseRole, int] = {
    EnterpriseRole.FRANCHISE_OWNER: 100,
    EnterpriseRole.ORG_ADMIN: 80,
    EnterpriseRole.REGIONAL_MANAGER: 60,
    EnterpriseRole.LOCATION_MANAGER: 40,
    EnterpriseRole.LOCATION_STAFF: 20,
    EnterpriseRole.AUDITOR: 30,
    EnterpriseRole.API_CLIENT: 10,
}


class SsoProvider(StrEnum):
    OIDC = "oidc"
    SAML = "saml"
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    OKTA = "okta"


class PolicyScope(StrEnum):
    ORGANIZATION = "organization"
    LOCATION = "location"


class PolicyEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_HUMAN = "require_human"


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    SSO = "sso"
    POLICY_EVAL = "policy_eval"
    GATEWAY = "gateway"
    VIEW = "view"
    EXPORT = "export"


class GatewayAuthType(StrEnum):
    JWT = "jwt"
    API_KEY = "api_key"
    SSO = "sso"
