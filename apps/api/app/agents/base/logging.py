"""Structured logging helpers for agents."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base.config import agent_settings


def get_agent_logger(agent_name: str) -> logging.Logger:
    logger = logging.getLogger(f"asa.agents.{agent_name}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s"
            )
        )
        logger.addHandler(handler)
        logger.propagate = False
    level = getattr(logging, agent_settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)
    return logger


def log_extra(
    *,
    correlation_id: str | None = None,
    shop_id: str | None = None,
    event_type: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if correlation_id:
        payload["correlation_id"] = correlation_id
    if shop_id:
        payload["shop_id"] = shop_id
    if event_type:
        payload["event_type"] = event_type
    payload.update(kwargs)
    return payload
