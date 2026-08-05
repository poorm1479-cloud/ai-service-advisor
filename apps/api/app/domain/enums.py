from enum import Enum


class AccountType(str, Enum):
    """Top-level account kind — shop registrant vs platform admin."""

    SHOP = "shop"
    PLATFORM_ADMIN = "platform_admin"


class UserRole(str, Enum):

    """Shop principal roles — not job titles.



    Legacy job-title values (manager, service_advisor, mechanic, …) are still

    accepted via :func:`normalize_user_role` and map to STAFF.

    """



    OWNER = "owner"

    STAFF = "staff"

    AI_AGENT = "ai_agent"





# Deprecated aliases kept for typing/docs only — prefer normalize_user_role()

LEGACY_USER_ROLES = frozenset(

    {

        "manager",

        "service_advisor",

        "mechanic",

        "receptionist",

        "technician",

        "serviceadvisor",

    }

)





ROLE_LABELS = {

    UserRole.OWNER: "Owner",

    UserRole.STAFF: "Staff",

    UserRole.AI_AGENT: "AI Agent",

}





def normalize_user_role(value: UserRole | str) -> UserRole:

    """Parse JWT / DB role strings with legacy job-title dual-read."""

    if isinstance(value, UserRole):

        # If somehow a legacy enum member existed, map it — current enum is clean

        raw = value.value

    else:

        raw = str(value or "").strip().lower()



    if raw in {UserRole.OWNER.value, "owner"}:

        return UserRole.OWNER

    if raw in {UserRole.AI_AGENT.value, "ai_agent", "ai-agent", "agent"}:

        return UserRole.AI_AGENT

    if raw in {UserRole.STAFF.value, "staff", *LEGACY_USER_ROLES}:

        return UserRole.STAFF

    # Unknown → staff (safe default for small-shop multi-function users)

    if raw:

        return UserRole.STAFF

    raise ValueError("Invalid role")





class CommunicationChannel(str, Enum):

    PHONE = "phone"

    SMS = "sms"

    EMAIL = "email"

    FACEBOOK = "facebook"

    WEBSITE_CHAT = "website_chat"

    WALK_IN = "walk_in"





class CommunicationDirection(str, Enum):

    INCOMING = "incoming"

    OUTGOING = "outgoing"





class WalkInStatus(str, Enum):

    OPEN = "open"

    CONVERTED = "converted"

    CLOSED = "closed"


