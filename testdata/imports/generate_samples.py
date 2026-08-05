"""Generate CSV/Excel sample files for import-engine testing."""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

OUT = Path(__file__).resolve().parent

# Dated around 2026-08-01 so "today" appointments / recent history look populated.
CUSTOMERS = [
    {
        "external_id": "C001",
        "name": "Alex Rivera",
        "phone": "555-0100",
        "email": "alex.rivera@example.com",
        "address": "120 Main St, Austin, TX",
    },
    {
        "external_id": "C002",
        "name": "Jordan Lee",
        "phone": "555-0142",
        "email": "jordan.lee@example.com",
        "address": "88 Oak Ave, Dallas, TX",
    },
    {
        "external_id": "C003",
        "name": "Sam Patel",
        "phone": "555-0199",
        "email": "sam.patel@example.com",
        "address": "41 Pine Rd, Houston, TX",
    },
    {
        "external_id": "C004",
        "name": "Casey Nguyen",
        "phone": "555-0221",
        "email": "casey.nguyen@example.com",
        "address": "9 Cedar Ln, San Antonio, TX",
    },
    {
        "external_id": "C005",
        "name": "Morgan Blake",
        "phone": "555-0288",
        "email": "morgan.blake@example.com",
        "address": "72 Willow Dr, Austin, TX",
    },
    {
        "external_id": "C006",
        "name": "Riley Chen",
        "phone": "555-0330",
        "email": "riley.chen@example.com",
        "address": "15 Maple Ct, Plano, TX",
    },
]

VEHICLES = [
    {
        "external_id": "V001",
        "vin": "1HGCM82633A004352",
        "year": 2019,
        "make": "Honda",
        "model": "Accord",
        "mileage": 48200,
        "license_plate": "TX-A4821",
        "customer_external_id": "C001",
    },
    {
        "external_id": "V002",
        "vin": "5YJSA1E2XHF000123",
        "year": 2017,
        "make": "Tesla",
        "model": "Model S",
        "mileage": 61000,
        "license_plate": "TX-EV901",
        "customer_external_id": "C002",
    },
    {
        "external_id": "V003",
        "vin": "1FTFW1ET9DFC10312",
        "year": 2013,
        "make": "Ford",
        "model": "F-150",
        "mileage": 128400,
        "license_plate": "TX-TRK22",
        "customer_external_id": "C003",
    },
    {
        "external_id": "V004",
        "vin": "2T1BURHE2JC074321",
        "year": 2018,
        "make": "Toyota",
        "model": "Corolla",
        "mileage": 55300,
        "license_plate": "TX-C7730",
        "customer_external_id": "C004",
    },
    {
        "external_id": "V005",
        "vin": "3VWDP7AJ2DM123456",
        "year": 2020,
        "make": "Volkswagen",
        "model": "Jetta",
        "mileage": 41200,
        "license_plate": "TX-VW412",
        "customer_external_id": "C005",
    },
    {
        "external_id": "V006",
        "vin": "1G1YY22G165123456",
        "year": 2021,
        "make": "Chevrolet",
        "model": "Corvette",
        "mileage": 18500,
        "license_plate": "TX-CV185",
        "customer_external_id": "C006",
    },
]

REPAIRS = [
    {
        "external_id": "R001",
        "vin": "1HGCM82633A004352",
        "customer_external_id": "C001",
        "service_type": "oil_change",
        "description": "Oil & filter change",
        "cost": "89.99",
        "mileage": 47000,
        "date": "2025-11-12",
        "recommendation": "Rotate tires next visit",
    },
    {
        "external_id": "R002",
        "vin": "5YJSA1E2XHF000123",
        "customer_external_id": "C002",
        "service_type": "brake_service",
        "description": "Front brake pad replacement",
        "cost": "420.00",
        "mileage": 59800,
        "date": "2026-01-08",
        "recommendation": "Inspect rotors in 6 months",
    },
    {
        "external_id": "R003",
        "vin": "1FTFW1ET9DFC10312",
        "customer_external_id": "C003",
        "service_type": "transmission",
        "description": "Transmission fluid flush",
        "cost": "279.50",
        "mileage": 126000,
        "date": "2026-02-20",
        "recommendation": "",
    },
    {
        "external_id": "R004",
        "vin": "2T1BURHE2JC074321",
        "customer_external_id": "C004",
        "service_type": "tire",
        "description": "4 tire mount & balance",
        "cost": "640.00",
        "mileage": 54000,
        "date": "2026-06-15",
        "recommendation": "Alignment recommended",
    },
    {
        "external_id": "R005",
        "vin": "3VWDP7AJ2DM123456",
        "customer_external_id": "C005",
        "service_type": "inspection",
        "description": "State inspection + cabin filter",
        "cost": "125.00",
        "mileage": 40500,
        "date": "2026-07-20",
        "recommendation": "Brake fluid flush soon",
    },
    {
        "external_id": "R006",
        "vin": "1G1YY22G165123456",
        "customer_external_id": "C006",
        "service_type": "oil_change",
        "description": "Synthetic oil change",
        "cost": "119.00",
        "mileage": 18000,
        "date": "2026-07-28",
        "recommendation": "",
    },
]

INVOICES = [
    {
        "external_id": "I001",
        "invoice_number": "INV-1001",
        "customer_external_id": "C001",
        "vin": "1HGCM82633A004352",
        "amount": "89.99",
        "tax": "7.42",
        "status": "paid",
        "date": "2025-11-12",
    },
    {
        "external_id": "I002",
        "invoice_number": "INV-1002",
        "customer_external_id": "C002",
        "vin": "5YJSA1E2XHF000123",
        "amount": "420.00",
        "tax": "34.65",
        "status": "paid",
        "date": "2026-01-08",
    },
    {
        "external_id": "I003",
        "invoice_number": "INV-1003",
        "customer_external_id": "C003",
        "vin": "1FTFW1ET9DFC10312",
        "amount": "279.50",
        "tax": "23.06",
        "status": "paid",
        "date": "2026-02-20",
    },
    {
        "external_id": "I004",
        "invoice_number": "INV-1004",
        "customer_external_id": "C005",
        "vin": "3VWDP7AJ2DM123456",
        "amount": "125.00",
        "tax": "10.31",
        "status": "paid",
        "date": "2026-07-20",
    },
    {
        "external_id": "I005",
        "invoice_number": "INV-1005",
        "customer_external_id": "C006",
        "vin": "1G1YY22G165123456",
        "amount": "119.00",
        "tax": "9.82",
        "status": "paid",
        "date": "2026-07-28",
    },
    {
        "external_id": "I006",
        "invoice_number": "INV-1006",
        "customer_external_id": "C001",
        "vin": "1HGCM82633A004352",
        "amount": "245.00",
        "tax": "20.21",
        "status": "open",
        "date": "2026-08-01",
    },
]

ESTIMATES = [
    {
        "external_id": "E001",
        "estimate_number": "EST-2001",
        "customer_external_id": "C004",
        "vin": "2T1BURHE2JC074321",
        "amount": "185.00",
        "status": "open",
        "date": "2026-07-25",
    },
    {
        "external_id": "E002",
        "estimate_number": "EST-2002",
        "customer_external_id": "C001",
        "vin": "1HGCM82633A004352",
        "amount": "950.00",
        "status": "declined",
        "date": "2026-07-28",
    },
    {
        "external_id": "E003",
        "estimate_number": "EST-2003",
        "customer_external_id": "C003",
        "vin": "1FTFW1ET9DFC10312",
        "amount": "1280.00",
        "status": "open",
        "date": "2026-07-30",
    },
]

APPOINTMENTS = [
    {
        "external_id": "A001",
        "customer_external_id": "C001",
        "vin": "1HGCM82633A004352",
        "start": "2026-08-01 09:00",
        "end": "2026-08-01 10:00",
        "repair_type": "oil_change",
        "status": "scheduled",
        "notes": "Customer prefers morning slot",
    },
    {
        "external_id": "A002",
        "customer_external_id": "C002",
        "vin": "5YJSA1E2XHF000123",
        "start": "2026-08-01 11:00",
        "end": "2026-08-01 13:00",
        "repair_type": "brake_service",
        "status": "in_progress",
        "notes": "Waiting on pads",
    },
    {
        "external_id": "A003",
        "customer_external_id": "C005",
        "vin": "3VWDP7AJ2DM123456",
        "start": "2026-08-01 14:00",
        "end": "2026-08-01 15:00",
        "repair_type": "inspection",
        "status": "waiting",
        "notes": "Walk-in approved",
    },
    {
        "external_id": "A004",
        "customer_external_id": "C006",
        "vin": "1G1YY22G165123456",
        "start": "2026-08-01 15:30",
        "end": "2026-08-01 16:30",
        "repair_type": "tire",
        "status": "scheduled",
        "notes": "",
    },
    {
        "external_id": "A005",
        "customer_external_id": "C003",
        "vin": "1FTFW1ET9DFC10312",
        "start": "2026-07-28 10:00",
        "end": "2026-07-28 12:00",
        "repair_type": "transmission",
        "status": "completed",
        "notes": "",
    },
]

COMMUNICATIONS = [
    {
        "external_id": "M001",
        "customer_external_id": "C001",
        "phone": "555-0100",
        "channel": "sms",
        "direction": "outbound",
        "message": "Reminder: oil change appointment tomorrow at 9:00 AM.",
        "date": "2026-07-31 16:00",
    },
    {
        "external_id": "M002",
        "customer_external_id": "C002",
        "phone": "555-0142",
        "channel": "sms",
        "direction": "inbound",
        "message": "Can I reschedule Friday appointment?",
        "date": "2026-07-30 11:12",
    },
    {
        "external_id": "M003",
        "customer_external_id": "C004",
        "phone": "555-0221",
        "channel": "email",
        "direction": "outbound",
        "message": "Your estimate EST-2001 is ready for review.",
        "date": "2026-07-25 09:45",
    },
]

RECOMMENDATIONS = [
    {
        "external_id": "REC001",
        "vin": "1HGCM82633A004352",
        "customer_external_id": "C001",
        "text": "Replace cabin air filter",
        "priority": "normal",
        "status": "open",
    },
    {
        "external_id": "REC002",
        "vin": "1FTFW1ET9DFC10312",
        "customer_external_id": "C003",
        "text": "Front suspension bushings worn",
        "priority": "high",
        "status": "open",
    },
    {
        "external_id": "REC003",
        "vin": "3VWDP7AJ2DM123456",
        "customer_external_id": "C005",
        "text": "Brake fluid flush recommended",
        "priority": "normal",
        "status": "open",
    },
]


def write_multi_entity_csv(path: Path) -> None:
    fieldnames = [
        "entity",
        "external_id",
        "name",
        "phone",
        "email",
        "address",
        "vin",
        "year",
        "make",
        "model",
        "mileage",
        "license_plate",
        "customer_external_id",
        "service_type",
        "description",
        "cost",
        "recommendation",
        "date",
        "invoice_number",
        "estimate_number",
        "amount",
        "tax",
        "status",
        "start",
        "end",
        "repair_type",
        "notes",
        "channel",
        "direction",
        "message",
        "text",
        "priority",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in CUSTOMERS:
            writer.writerow({"entity": "customer", **row})
        for row in VEHICLES:
            writer.writerow({"entity": "vehicle", **row})
        for row in REPAIRS:
            writer.writerow({"entity": "repair", **row})
        for row in INVOICES:
            writer.writerow({"entity": "invoice", **row})
        for row in ESTIMATES:
            writer.writerow({"entity": "estimate", **row})
        for row in APPOINTMENTS:
            writer.writerow({"entity": "appointment", **row})
        for row in COMMUNICATIONS:
            writer.writerow({"entity": "communication", **row})
        for row in RECOMMENDATIONS:
            writer.writerow({"entity": "recommendation", **row})


def write_customers_csv(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["external_id", "name", "phone", "email", "address"]
        )
        writer.writeheader()
        writer.writerows(CUSTOMERS)


def add_sheet(wb: Workbook, name: str, rows: list[dict], columns: list[str]) -> None:
    ws = wb.create_sheet(name)
    ws.append(columns)
    for row in rows:
        ws.append([row.get(col, "") for col in columns])


def write_excel(path: Path) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    add_sheet(
        wb,
        "customers",
        CUSTOMERS,
        ["external_id", "name", "phone", "email", "address"],
    )
    add_sheet(
        wb,
        "vehicles",
        VEHICLES,
        [
            "external_id",
            "vin",
            "year",
            "make",
            "model",
            "mileage",
            "license_plate",
            "customer_external_id",
        ],
    )
    add_sheet(
        wb,
        "repairs",
        REPAIRS,
        [
            "external_id",
            "vin",
            "customer_external_id",
            "service_type",
            "description",
            "cost",
            "mileage",
            "date",
            "recommendation",
        ],
    )
    add_sheet(
        wb,
        "invoices",
        INVOICES,
        [
            "external_id",
            "invoice_number",
            "customer_external_id",
            "vin",
            "amount",
            "tax",
            "status",
            "date",
        ],
    )
    add_sheet(
        wb,
        "estimates",
        ESTIMATES,
        [
            "external_id",
            "estimate_number",
            "customer_external_id",
            "vin",
            "amount",
            "status",
            "date",
        ],
    )
    add_sheet(
        wb,
        "appointments",
        APPOINTMENTS,
        [
            "external_id",
            "customer_external_id",
            "vin",
            "start",
            "end",
            "repair_type",
            "status",
            "notes",
        ],
    )
    add_sheet(
        wb,
        "communications",
        COMMUNICATIONS,
        [
            "external_id",
            "customer_external_id",
            "phone",
            "channel",
            "direction",
            "message",
            "date",
        ],
    )
    add_sheet(
        wb,
        "recommendations",
        RECOMMENDATIONS,
        ["external_id", "vin", "customer_external_id", "text", "priority", "status"],
    )
    wb.save(path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    multi_csv = OUT / "shop_import_sample.csv"
    customers_csv = OUT / "customers_only.csv"
    xlsx = OUT / "shop_import_sample.xlsx"
    write_multi_entity_csv(multi_csv)
    write_customers_csv(customers_csv)
    write_excel(xlsx)
    for path in (multi_csv, customers_csv, xlsx):
        print(f"{path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
