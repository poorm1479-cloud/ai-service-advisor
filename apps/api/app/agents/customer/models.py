"""Customer agent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class CustomerProfile:
    id: UUID
    shop_id: UUID
    name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CustomerResolveRequest:
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    create_if_missing: bool = True
    prefer_customer_id: UUID | None = None


@dataclass(slots=True)
class CustomerResolveResult:
    customer: CustomerProfile | None
    is_new: bool = False
    merged_from: list[UUID] = field(default_factory=list)
    action: str = "none"
    # AI Decision Layer — proposed mutation; Workflow executes it
    decision: Any | None = None
