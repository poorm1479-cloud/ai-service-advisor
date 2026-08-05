"""Agent framework configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Tunables for the agent runtime (env prefix AGENT_)."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        env_prefix="AGENT_",
        extra="ignore",
    )

    enabled: bool = True
    log_level: str = "INFO"
    retry_max_attempts: int = 3
    retry_base_delay_ms: int = 50
    retry_max_delay_ms: int = 2000
    retry_jitter: bool = True
    bus_max_handlers_per_event: int = 32
    default_timezone: str = "America/Chicago"
    escalate_on_emergency: bool = True
    escalate_on_complaint: bool = True
    mcp_enabled: bool = True


agent_settings = AgentSettings()
