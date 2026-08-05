"""Marketing monitoring counters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MarketingMonitor:
    campaigns_created: int = 0
    campaigns_scheduled: int = 0
    messages_sent: int = 0
    retries: int = 0
    by_channel: dict[str, int] = field(default_factory=dict)
    by_type: dict[str, int] = field(default_factory=dict)

    def record_created(self, campaign_type: str) -> None:
        self.campaigns_created += 1
        self.by_type[campaign_type] = self.by_type.get(campaign_type, 0) + 1

    def record_scheduled(self) -> None:
        self.campaigns_scheduled += 1

    def record_sent(self, channel: str) -> None:
        self.messages_sent += 1
        self.by_channel[channel] = self.by_channel.get(channel, 0) + 1

    def record_retry(self) -> None:
        self.retries += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "campaigns_created": self.campaigns_created,
            "campaigns_scheduled": self.campaigns_scheduled,
            "messages_sent": self.messages_sent,
            "retries": self.retries,
            "by_channel": dict(self.by_channel),
            "by_type": dict(self.by_type),
        }
