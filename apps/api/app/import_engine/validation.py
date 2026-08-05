"""AI validation: duplicates, VIN, mileage consistency, merge suggestions."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from app.import_engine.enums import (
    DuplicateMatchType,
    EntityKind,
    MergeAction,
    ValidationSeverity,
)
from app.import_engine.models import (
    CanonicalCustomer,
    CanonicalVehicle,
    DuplicateCandidate,
    NormalizedBatch,
    ValidationIssue,
)
from app.import_engine.normalize import normalize_name
from app.import_engine.store import ImportStorePort
from app.import_engine.vin import normalize_vin, validate_vin


def _customer_ref(c: CanonicalCustomer, index: int) -> str:
    return c.row_ref or c.external_id or f"customer:{index}"


def _vehicle_ref(v: CanonicalVehicle, index: int) -> str:
    return v.row_ref or v.external_id or v.vin or f"vehicle:{index}"


def _customer_snap(c: CanonicalCustomer) -> dict[str, Any]:
    return {
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "address": c.address,
        "external_id": c.external_id,
    }


def _vehicle_snap(v: CanonicalVehicle) -> dict[str, Any]:
    return {
        "vin": v.vin,
        "year": v.year,
        "make": v.make,
        "model": v.model,
        "mileage": v.mileage,
        "license_plate": v.license_plate,
        "external_id": v.external_id,
    }


class ValidationEngine:
    """Detect duplicates, invalid VINs, and inconsistent mileage."""

    async def validate(
        self,
        batch: NormalizedBatch,
        *,
        shop_id: UUID,
        store: ImportStorePort,
    ) -> tuple[list[ValidationIssue], list[DuplicateCandidate]]:
        issues: list[ValidationIssue] = []
        duplicates: list[DuplicateCandidate] = []

        issues.extend(self._validate_vins(batch))
        issues.extend(self._validate_mileage(batch))
        duplicates.extend(self._detect_customer_duplicates_in_batch(batch))
        duplicates.extend(self._detect_vehicle_duplicates_in_batch(batch))
        duplicates.extend(await self._detect_customer_duplicates_against_store(batch, shop_id, store))
        duplicates.extend(await self._detect_vehicle_duplicates_against_store(batch, shop_id, store))
        return issues, duplicates

    def _validate_vins(self, batch: NormalizedBatch) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for i, v in enumerate(batch.vehicles):
            ok, err = validate_vin(v.vin)
            if not ok:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="invalid_vin",
                        message=err or "Invalid VIN",
                        entity_kind=EntityKind.VEHICLE,
                        entity_ref=_vehicle_ref(v, i),
                        details={"vin": v.vin},
                    )
                )
            else:
                v.vin = normalize_vin(v.vin) or v.vin
        for i, r in enumerate(batch.repairs):
            if r.vehicle_vin:
                ok, err = validate_vin(r.vehicle_vin)
                if not ok:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            code="repair_invalid_vin",
                            message=err or "Repair references invalid VIN",
                            entity_kind=EntityKind.REPAIR_HISTORY,
                            entity_ref=r.row_ref or f"repair:{i}",
                            details={"vin": r.vehicle_vin},
                        )
                    )
        return issues

    def _validate_mileage(self, batch: NormalizedBatch) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        # Compare repair readings only. Vehicle odometer is "current" and is often
        # higher than historical repair mileage — that is not inconsistent.
        repairs_by_vin: dict[str, list[tuple[int, datetime | None, str]]] = defaultdict(list)

        for i, v in enumerate(batch.vehicles):
            if v.mileage is not None and v.mileage < 0:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="negative_mileage",
                        message="Mileage cannot be negative",
                        entity_kind=EntityKind.VEHICLE,
                        entity_ref=_vehicle_ref(v, i),
                    )
                )

        for i, r in enumerate(batch.repairs):
            if r.vehicle_vin and r.mileage_at_service is not None:
                repairs_by_vin[r.vehicle_vin].append(
                    (r.mileage_at_service, r.performed_at, r.row_ref or f"repair:{i}")
                )

        for vin, samples in repairs_by_vin.items():
            dated = [(m, dt, ref) for m, dt, ref in samples if dt is not None]
            undated = [(m, ref) for m, _dt, ref in samples if _dt is None]
            dated.sort(key=lambda item: item[1])
            ordered: list[tuple[int, str]] = [(m, ref) for m, _dt, ref in dated] + undated
            if len(ordered) < 2:
                continue
            max_seen = -1
            for mileage, ref in ordered:
                if mileage < max_seen:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            code="inconsistent_mileage",
                            message=f"Mileage decreased for VIN {vin} ({mileage} < {max_seen})",
                            entity_kind=EntityKind.VEHICLE,
                            entity_ref=ref,
                            details={"vin": vin, "mileage": mileage, "previous_max": max_seen},
                        )
                    )
                max_seen = max(max_seen, mileage)

        for vin in {v.vin for v in batch.vehicles if v.vin} | {
            r.vehicle_vin for r in batch.repairs if r.vehicle_vin
        }:
            vehicle_miles = [v.mileage for v in batch.vehicles if v.vin == vin and v.mileage is not None]
            repair_miles = [
                r.mileage_at_service
                for r in batch.repairs
                if r.vehicle_vin == vin and r.mileage_at_service is not None
            ]
            if vehicle_miles and repair_miles and max(repair_miles) > max(vehicle_miles) + 5000:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.INFO,
                        code="mileage_ahead_of_vehicle",
                        message=f"Repair mileage exceeds vehicle odometer for VIN {vin}",
                        entity_kind=EntityKind.VEHICLE,
                        entity_ref=vin,
                        details={"vehicle_mileage": max(vehicle_miles), "repair_mileage": max(repair_miles)},
                    )
                )
        return issues

    def _detect_customer_duplicates_in_batch(self, batch: NormalizedBatch) -> list[DuplicateCandidate]:
        dups: list[DuplicateCandidate] = []
        by_phone: dict[str, list[tuple[int, CanonicalCustomer]]] = defaultdict(list)
        by_email: dict[str, list[tuple[int, CanonicalCustomer]]] = defaultdict(list)
        by_name: dict[str, list[tuple[int, CanonicalCustomer]]] = defaultdict(list)

        for i, c in enumerate(batch.customers):
            if c.phone:
                by_phone[c.phone].append((i, c))
            if c.email:
                by_email[c.email].append((i, c))
            if c.name:
                by_name[normalize_name(c.name).lower()].append((i, c))

        seen_pairs: set[tuple[str, str]] = set()

        def add_pair(
            a: tuple[int, CanonicalCustomer],
            b: tuple[int, CanonicalCustomer],
            match: DuplicateMatchType,
            confidence: float,
        ) -> None:
            ref_a, ref_b = _customer_ref(a[1], a[0]), _customer_ref(b[1], b[0])
            key = tuple(sorted((ref_a, ref_b)))
            if key in seen_pairs or ref_a == ref_b:
                return
            seen_pairs.add(key)
            dups.append(
                DuplicateCandidate(
                    entity_kind=EntityKind.CUSTOMER,
                    match_type=match,
                    confidence=confidence,
                    incoming_ref=ref_a,
                    existing_ref=ref_b,
                    incoming_snapshot=_customer_snap(a[1]),
                    existing_snapshot=_customer_snap(b[1]),
                    suggested_action=MergeAction.MERGE,
                )
            )

        for group in by_phone.values():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    add_pair(group[i], group[j], DuplicateMatchType.PHONE, 0.95)
        for group in by_email.values():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    add_pair(group[i], group[j], DuplicateMatchType.EMAIL, 0.9)
        for group in by_name.values():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    # Name-only match is weaker unless phones both empty
                    conf = 0.55
                    if not group[i][1].phone and not group[j][1].phone:
                        conf = 0.7
                    add_pair(group[i], group[j], DuplicateMatchType.NAME, conf)
        return dups

    def _detect_vehicle_duplicates_in_batch(self, batch: NormalizedBatch) -> list[DuplicateCandidate]:
        dups: list[DuplicateCandidate] = []
        by_vin: dict[str, list[tuple[int, CanonicalVehicle]]] = defaultdict(list)
        for i, v in enumerate(batch.vehicles):
            if v.vin:
                by_vin[v.vin].append((i, v))
        for group in by_vin.values():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    dups.append(
                        DuplicateCandidate(
                            entity_kind=EntityKind.VEHICLE,
                            match_type=DuplicateMatchType.VIN,
                            confidence=0.99,
                            incoming_ref=_vehicle_ref(a[1], a[0]),
                            existing_ref=_vehicle_ref(b[1], b[0]),
                            incoming_snapshot=_vehicle_snap(a[1]),
                            existing_snapshot=_vehicle_snap(b[1]),
                            suggested_action=MergeAction.MERGE,
                        )
                    )
        return dups

    async def _detect_customer_duplicates_against_store(
        self, batch: NormalizedBatch, shop_id: UUID, store: ImportStorePort
    ) -> list[DuplicateCandidate]:
        dups: list[DuplicateCandidate] = []
        for i, c in enumerate(batch.customers):
            matches = []
            if c.phone:
                matches.extend(await store.find_customers_by_phone(shop_id, c.phone))
            if c.email:
                matches.extend(await store.find_customers_by_email(shop_id, c.email))
            seen: set[UUID] = set()
            for rec in matches:
                if rec.id in seen:
                    continue
                seen.add(rec.id)
                dups.append(
                    DuplicateCandidate(
                        entity_kind=EntityKind.CUSTOMER,
                        match_type=DuplicateMatchType.COMPOSITE,
                        confidence=0.92,
                        incoming_ref=_customer_ref(c, i),
                        existing_ref=str(rec.id),
                        incoming_snapshot=_customer_snap(c),
                        existing_snapshot=dict(rec.payload),
                        suggested_action=MergeAction.MERGE,
                    )
                )
        return dups

    async def _detect_vehicle_duplicates_against_store(
        self, batch: NormalizedBatch, shop_id: UUID, store: ImportStorePort
    ) -> list[DuplicateCandidate]:
        dups: list[DuplicateCandidate] = []
        for i, v in enumerate(batch.vehicles):
            if not v.vin:
                continue
            for rec in await store.find_vehicles_by_vin(shop_id, v.vin):
                dups.append(
                    DuplicateCandidate(
                        entity_kind=EntityKind.VEHICLE,
                        match_type=DuplicateMatchType.VIN,
                        confidence=0.99,
                        incoming_ref=_vehicle_ref(v, i),
                        existing_ref=str(rec.id),
                        incoming_snapshot=_vehicle_snap(v),
                        existing_snapshot=dict(rec.payload),
                        suggested_action=MergeAction.MERGE,
                    )
                )
        return dups

    def merge_customer(self, primary: CanonicalCustomer, secondary: CanonicalCustomer) -> CanonicalCustomer:
        return CanonicalCustomer(
            external_id=primary.external_id or secondary.external_id,
            name=primary.name or secondary.name,
            phone=primary.phone or secondary.phone,
            email=primary.email or secondary.email,
            address=primary.address or secondary.address,
            source=primary.source,
            metadata={**secondary.metadata, **primary.metadata},
            row_ref=primary.row_ref or secondary.row_ref,
        )

    def merge_vehicle(self, primary: CanonicalVehicle, secondary: CanonicalVehicle) -> CanonicalVehicle:
        return CanonicalVehicle(
            external_id=primary.external_id or secondary.external_id,
            vin=primary.vin or secondary.vin,
            year=primary.year or secondary.year,
            make=primary.make or secondary.make,
            model=primary.model or secondary.model,
            mileage=(
                max(m for m in (primary.mileage, secondary.mileage) if m is not None)
                if primary.mileage is not None or secondary.mileage is not None
                else None
            ),
            license_plate=primary.license_plate or secondary.license_plate,
            customer_external_id=primary.customer_external_id or secondary.customer_external_id,
            customer_phone=primary.customer_phone or secondary.customer_phone,
            customer_name=primary.customer_name or secondary.customer_name,
            source=primary.source,
            metadata={**secondary.metadata, **primary.metadata},
            row_ref=primary.row_ref or secondary.row_ref,
        )
