"""Google Calendar adapter."""

from __future__ import annotations

from app.mcp_hub.adapters.base import BaseAdapter
from app.mcp_hub.enums import AuthMethod, IntegrationCategory, IntegrationProvider


class GoogleCalendarAdapter(BaseAdapter):
    provider = IntegrationProvider.GOOGLE_CALENDAR
    display_name = "Google Calendar"
    description = "Sync shop appointments and technician calendars."
    category = IntegrationCategory.CALENDAR
    auth_method = AuthMethod.OAUTH2
    api_version = "v3"
    capabilities = ["events.read", "events.write"]
    required_scopes = ["calendar.events"]
    credential_fields = ["client_id", "client_secret", "refresh_token"]
    docs_url = "https://developers.google.com/calendar"
    tool_defs = [
        (
            "google_calendar.list_events",
            "List calendar events in a range",
            {
                "type": "object",
                "properties": {"calendar_id": {"type": "string"}, "time_min": {"type": "string"}, "time_max": {"type": "string"}},
            },
            ["calendar", "read"],
        ),
        (
            "google_calendar.create_event",
            "Create a calendar event",
            {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["summary", "start", "end"],
            },
            ["calendar", "write"],
        ),
    ]
