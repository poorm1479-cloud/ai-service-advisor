"""Integration layer enumerations."""

from __future__ import annotations

from enum import StrEnum


class IntegrationCategory(StrEnum):
    DMS = "dms"
    ACCOUNTING = "accounting"
    COMMUNICATION = "communication"
    PAYMENT = "payment"


class IntegrationProvider(StrEnum):
    # DMS
    SHOPMONKEY = "shopmonkey"
    TEKMETRIC = "tekmetric"
    AUTOLEAP = "autoleap"
    MITCHELL = "mitchell"
    # Accounting
    QUICKBOOKS = "quickbooks"
    # Communication
    TWILIO = "twilio"
    EMAIL = "email"
    # Payment
    STRIPE = "stripe"


class ConnectionStatus(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


class IntegrationCapability(StrEnum):
    """Capabilities exposed by the External Integration Layer."""

    IMPORT_CUSTOMER_DATA = "ImportCustomerData"
    IMPORT_VEHICLE_DATA = "ImportVehicleData"
    IMPORT_REPAIR_HISTORY = "ImportRepairHistory"
    SYNC_APPOINTMENT = "SyncAppointment"
    SYNC_INVOICE = "SyncInvoice"
    SYNC_PAYMENT = "SyncPayment"
    SEND_CUSTOMER_MESSAGE = "SendCustomerMessage"
    RECEIVE_CUSTOMER_MESSAGE = "ReceiveCustomerMessage"


class AuthMethod(StrEnum):
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BASIC = "basic"
    WEBHOOK = "webhook"
