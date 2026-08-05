"""Synthetic entity generators for the Auto Repair Simulation Engine."""

from __future__ import annotations

import random
from uuid import uuid4

from app.simulation.models import (
    SyntheticAppointment,
    SyntheticConversation,
    SyntheticCustomer,
    SyntheticEstimate,
    SyntheticInspection,
    SyntheticPayment,
    SyntheticRepairRequest,
    SyntheticVehicle,
)

_FIRST = ["Alex", "Jordan", "Casey", "Riley", "Morgan", "Sam", "Taylor", "Quinn", "Avery", "Jamie"]
_LAST = ["Rivera", "Lee", "Nguyen", "Patel", "Garcia", "Kim", "Brooks", "Chen", "Murphy", "Diaz"]
_MAKES = {
    "Honda": ["Accord", "Civic", "CR-V"],
    "Toyota": ["Camry", "Corolla", "RAV4"],
    "Ford": ["F-150", "Escape", "Explorer"],
    "Chevrolet": ["Malibu", "Equinox", "Silverado"],
    "Tesla": ["Model 3", "Model Y", "Model S"],
}
_COMPLAINTS = [
    ("brake noise", "brake_inspection", 320.0),
    ("check engine light", "diagnostics", 150.0),
    ("oil leak", "oil_change", 89.0),
    ("AC not cooling", "ac_service", 280.0),
    ("battery drain", "battery_test", 180.0),
    ("tire vibration", "tire_balance", 120.0),
]


def _vin(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return "".join(rng.choice(alphabet) for _ in range(17))


class EntityGenerator:
    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def customer(self) -> SyntheticCustomer:
        first = self._rng.choice(_FIRST)
        last = self._rng.choice(_LAST)
        n = self._rng.randint(1000, 9999)
        return SyntheticCustomer(
            id=uuid4(),
            name=f"{first} {last}",
            phone=f"+1555{n:07d}"[:12],
            email=f"{first.lower()}.{last.lower()}{n}@example.com",
            retention_score=round(self._rng.uniform(0.35, 0.98), 3),
        )

    def vehicle(self, customer_id: SyntheticCustomer | None = None) -> SyntheticVehicle:
        make = self._rng.choice(list(_MAKES.keys()))
        model = self._rng.choice(_MAKES[make])
        return SyntheticVehicle(
            id=uuid4(),
            customer_id=customer_id.id if customer_id else None,
            vin=_vin(self._rng),
            year=self._rng.randint(2008, 2025),
            make=make,
            model=model,
            mileage=self._rng.randint(5_000, 180_000),
            health_score=round(self._rng.uniform(45.0, 97.0), 1),
        )

    def conversation(
        self,
        *,
        customer: SyntheticCustomer | None,
        channel: str,
        body: str,
        intent: str,
    ) -> SyntheticConversation:
        return SyntheticConversation(
            id=uuid4(),
            customer_id=customer.id if customer else None,
            channel=channel,
            body=body,
            intent=intent,
        )

    def repair_request(
        self,
        *,
        customer: SyntheticCustomer | None,
        vehicle: SyntheticVehicle | None,
        complaint: str | None = None,
    ) -> SyntheticRepairRequest:
        if complaint:
            match = next((c for c in _COMPLAINTS if c[0] in complaint.lower()), None)
            service, cost = (match[1], match[2]) if match else ("general_inspection", 200.0)
            text = complaint
        else:
            text, service, cost = self._rng.choice(_COMPLAINTS)
            cost = round(cost * self._rng.uniform(0.85, 1.35), 2)
        return SyntheticRepairRequest(
            id=uuid4(),
            customer_id=customer.id if customer else None,
            vehicle_id=vehicle.id if vehicle else None,
            complaint=text,
            recommended_service=service,
            estimated_cost=cost,
        )

    def appointment(
        self,
        *,
        customer: SyntheticCustomer | None,
        vehicle: SyntheticVehicle | None,
        repair_type: str,
        booked: bool | None = None,
    ) -> SyntheticAppointment:
        will_book = self._rng.random() < 0.72 if booked is None else booked
        return SyntheticAppointment(
            id=uuid4(),
            customer_id=customer.id if customer else None,
            vehicle_id=vehicle.id if vehicle else None,
            repair_type=repair_type,
            booked=will_book,
        )

    def inspection(self, vehicle: SyntheticVehicle | None) -> SyntheticInspection:
        findings = self._rng.sample(
            ["pad wear", "rotor scoring", "fluid low", "sensor fault", "belt crack"],
            k=self._rng.randint(1, 3),
        )
        return SyntheticInspection(id=uuid4(), vehicle_id=vehicle.id if vehicle else None, findings=findings)

    def estimate(
        self,
        *,
        customer: SyntheticCustomer | None,
        amount: float,
        status: str | None = None,
    ) -> SyntheticEstimate:
        if status is None:
            status = self._rng.choices(
                ["sent", "approved", "declined"],
                weights=[0.25, 0.45, 0.30],
            )[0]
        return SyntheticEstimate(
            id=uuid4(),
            customer_id=customer.id if customer else None,
            amount=round(amount, 2),
            status=status,
        )

    def payment(self, *, amount: float, paid: bool | None = None) -> SyntheticPayment:
        return SyntheticPayment(
            id=uuid4(),
            invoice_id=uuid4(),
            amount=round(amount, 2),
            paid=self._rng.random() < 0.88 if paid is None else paid,
        )

    def decision_confidence(self, base: float = 0.82) -> float:
        return round(min(0.99, max(0.4, self._rng.gauss(base, 0.08))), 3)

    def choice(self, items: list):
        return self._rng.choice(items)

    def random(self) -> random.Random:
        return self._rng
