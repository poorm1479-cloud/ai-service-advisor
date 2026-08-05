"""Default MCP tools backed by specialized agents + Workflow DecisionExecutor.

AI tools propose Decisions; Workflow applies mutations (architecture rule).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.agents.base.agent import AgentContext
from app.agents.crm.models import CrmUpdateRequest
from app.agents.customer.models import CustomerResolveRequest
from app.agents.decisions.bridge import apply_decisions, collect_decision, ports_from_agents
from app.agents.marketing.models import MarketingActionType, MarketingRequest
from app.agents.mcp.registry import McpTool
from app.agents.revenue.models import RevenueAnalysisRequest
from app.agents.scheduling.models import SchedulingAction, SchedulingRequest
from app.agents.vehicle.models import VehicleResolveRequest


def build_default_mcp_tools(**agents: Any) -> list[McpTool]:
    customer = agents.get("customer")
    vehicle = agents.get("vehicle")
    scheduling = agents.get("scheduling")
    crm = agents.get("crm")
    revenue = agents.get("revenue")
    marketing = agents.get("marketing")

    ports = ports_from_agents(
        customer=customer,
        vehicle=vehicle,
        scheduling=scheduling,
        crm=crm,
        marketing=marketing,
    )

    tools: list[McpTool] = []

    if customer:

        async def find_or_create_customer(args: dict[str, Any]) -> dict[str, Any]:
            ctx = AgentContext(shop_id=UUID(args["shop_id"]))
            result = await customer.resolve(
                CustomerResolveRequest(
                    name=args.get("name"),
                    phone=args.get("phone"),
                    email=args.get("email"),
                    create_if_missing=args.get("create_if_missing", True),
                ),
                ctx,
            )
            decision = collect_decision(result)
            if decision is not None:
                applied = await apply_decisions(
                    shop_id=ctx.shop_id, decisions=[decision], ports=ports, context=ctx
                )
                if applied and applied.customer_result:
                    result = type(result)(
                        success=True,
                        data=applied.customer_result,
                    )
            data = result.data
            return {
                "success": result.success,
                "action": data.action if data else None,
                "customer_id": str(data.customer.id) if data and data.customer else None,
                "is_new": data.is_new if data else False,
            }

        tools.append(
            McpTool(
                name="customer.find_or_create",
                description="Find an existing customer or create one",
                input_schema={
                    "type": "object",
                    "required": ["shop_id"],
                    "properties": {
                        "shop_id": {"type": "string", "format": "uuid"},
                        "name": {"type": "string"},
                        "phone": {"type": "string"},
                        "email": {"type": "string"},
                        "create_if_missing": {"type": "boolean"},
                    },
                },
                handler=find_or_create_customer,
                agent="customer",
                tags=["crm"],
            )
        )

    if vehicle:

        async def resolve_vehicle(args: dict[str, Any]) -> dict[str, Any]:
            ctx = AgentContext(
                shop_id=UUID(args["shop_id"]),
                customer_id=UUID(args["customer_id"]) if args.get("customer_id") else None,
            )
            result = await vehicle.resolve(
                VehicleResolveRequest(
                    vin=args.get("vin"),
                    customer_id=ctx.customer_id,
                    mileage=args.get("mileage"),
                    create_if_missing=args.get("create_if_missing", False),
                ),
                ctx,
            )
            decision = collect_decision(result)
            if decision is not None:
                applied = await apply_decisions(
                    shop_id=ctx.shop_id, decisions=[decision], ports=ports, context=ctx
                )
                if applied and applied.vehicle_result:
                    from app.agents.base.agent import AgentResult

                    result = AgentResult.ok(applied.vehicle_result)
            data = result.data
            return {
                "success": result.success,
                "vehicle_id": str(data.vehicle.id) if data and data.vehicle else None,
                "action": data.action if data else None,
            }

        tools.append(
            McpTool(
                name="vehicle.resolve",
                description="Find a vehicle by VIN or customer",
                input_schema={
                    "type": "object",
                    "required": ["shop_id"],
                    "properties": {
                        "shop_id": {"type": "string", "format": "uuid"},
                        "vin": {"type": "string"},
                        "customer_id": {"type": "string", "format": "uuid"},
                        "mileage": {"type": "integer"},
                        "create_if_missing": {"type": "boolean"},
                    },
                },
                handler=resolve_vehicle,
                agent="vehicle",
                tags=["crm"],
            )
        )

    if scheduling:

        async def list_slots(args: dict[str, Any]) -> dict[str, Any]:
            ctx = AgentContext(shop_id=UUID(args["shop_id"]))
            result = await scheduling.process(
                SchedulingRequest(
                    action=SchedulingAction.LIST_SLOTS,
                    days_ahead=int(args.get("days_ahead", 7)),
                ),
                ctx,
            )
            data = result.data
            return {
                "success": result.success,
                "slots": [
                    {"start": s.start.isoformat(), "end": s.end.isoformat()}
                    for s in (data.available_slots if data else [])
                ],
            }

        tools.append(
            McpTool(
                name="scheduling.list_slots",
                description="List available appointment slots",
                input_schema={
                    "type": "object",
                    "required": ["shop_id"],
                    "properties": {
                        "shop_id": {"type": "string", "format": "uuid"},
                        "days_ahead": {"type": "integer", "default": 7},
                    },
                },
                handler=list_slots,
                agent="scheduling",
                tags=["scheduling"],
            )
        )

        async def book_appointment(args: dict[str, Any]) -> dict[str, Any]:
            from app.agents.base.agent import AgentResult

            ctx = AgentContext(
                shop_id=UUID(args["shop_id"]),
                customer_id=UUID(args["customer_id"]) if args.get("customer_id") else None,
                vehicle_id=UUID(args["vehicle_id"]) if args.get("vehicle_id") else None,
            )
            result = await scheduling.process(
                SchedulingRequest(
                    action=SchedulingAction.BOOK,
                    requested_service=args.get("service") or args.get("requested_service"),
                    service_id=UUID(args["service_id"]) if args.get("service_id") else None,
                ),
                ctx,
            )
            decision = collect_decision(result)
            if decision is not None:
                applied = await apply_decisions(
                    shop_id=ctx.shop_id, decisions=[decision], ports=ports, context=ctx
                )
                if applied and applied.scheduling_result:
                    result = AgentResult.ok(applied.scheduling_result)
            data = result.data
            return {
                "success": bool(data and data.success),
                "appointment_id": str(data.appointment.id) if data and data.appointment else None,
                "message": data.message if data else result.error,
            }

        tools.append(
            McpTool(
                name="scheduling.book",
                description=(
                    "Propose booking via AppointmentDecision (Service Catalog match); "
                    "Workflow validates availability and creates the appointment"
                ),
                input_schema={
                    "type": "object",
                    "required": ["shop_id"],
                    "properties": {
                        "shop_id": {"type": "string", "format": "uuid"},
                        "customer_id": {"type": "string", "format": "uuid"},
                        "vehicle_id": {"type": "string", "format": "uuid"},
                        "service": {
                            "type": "string",
                            "description": "Requested service name (matched to catalog)",
                        },
                        "requested_service": {"type": "string"},
                        "service_id": {"type": "string", "format": "uuid"},
                    },
                },
                handler=book_appointment,
                agent="scheduling",
                tags=["scheduling"],
            )
        )

    if crm:

        async def update_crm(args: dict[str, Any]) -> dict[str, Any]:
            from app.agents.base.agent import AgentResult

            ctx = AgentContext(
                shop_id=UUID(args["shop_id"]),
                customer_id=UUID(args["customer_id"]) if args.get("customer_id") else None,
            )
            result = await crm.update(
                CrmUpdateRequest(
                    customer_id=ctx.customer_id,
                    channel=args.get("channel"),
                    message=args.get("message"),
                    intent=args.get("intent"),
                ),
                ctx,
            )
            decision = collect_decision(result)
            if decision is not None:
                applied = await apply_decisions(
                    shop_id=ctx.shop_id, decisions=[decision], ports=ports, context=ctx
                )
                if applied and applied.crm_result:
                    result = AgentResult.ok(applied.crm_result)
            data = result.data
            return {
                "success": result.success,
                "summary": data.customer_summary if data else None,
            }

        tools.append(
            McpTool(
                name="crm.update_timeline",
                description="Record communication and update customer timeline",
                input_schema={
                    "type": "object",
                    "required": ["shop_id"],
                    "properties": {
                        "shop_id": {"type": "string", "format": "uuid"},
                        "customer_id": {"type": "string", "format": "uuid"},
                        "channel": {"type": "string"},
                        "message": {"type": "string"},
                        "intent": {"type": "string"},
                    },
                },
                handler=update_crm,
                agent="crm",
                tags=["crm"],
            )
        )

    if revenue:

        async def analyze_revenue(args: dict[str, Any]) -> dict[str, Any]:
            ctx = AgentContext(shop_id=UUID(args["shop_id"]))
            result = await revenue.analyze(
                RevenueAnalysisRequest(
                    customer_id=UUID(args["customer_id"]) if args.get("customer_id") else None,
                    days_since_last_visit=args.get("days_since_last_visit"),
                    intent=args.get("intent"),
                ),
                ctx,
            )
            data = result.data
            return {
                "success": result.success,
                "predicted_revenue": str(data.predicted_revenue) if data else "0",
                "lost_customer_risk": data.lost_customer_risk if data else 0,
                "upsell_count": len(data.upsell_opportunities) if data else 0,
            }

        tools.append(
            McpTool(
                name="revenue.analyze",
                description="Analyze upsell opportunities and churn risk",
                input_schema={
                    "type": "object",
                    "required": ["shop_id"],
                    "properties": {
                        "shop_id": {"type": "string", "format": "uuid"},
                        "customer_id": {"type": "string", "format": "uuid"},
                        "days_since_last_visit": {"type": "integer"},
                        "intent": {"type": "string"},
                    },
                },
                handler=analyze_revenue,
                agent="revenue",
                tags=["revenue"],
            )
        )

    if marketing:

        async def send_thank_you(args: dict[str, Any]) -> dict[str, Any]:
            from app.agents.base.agent import AgentResult

            ctx = AgentContext(
                shop_id=UUID(args["shop_id"]),
                customer_id=UUID(args["customer_id"]) if args.get("customer_id") else None,
            )
            result = await marketing.execute(
                MarketingRequest(
                    action_type=MarketingActionType.THANK_YOU,
                    channel=args.get("channel", "sms"),
                    customer_id=ctx.customer_id,
                    context={"name": args.get("name", ""), "shop": args.get("shop", "our shop")},
                ),
                ctx,
            )
            decision = collect_decision(result)
            if decision is not None:
                applied = await apply_decisions(
                    shop_id=ctx.shop_id, decisions=[decision], ports=ports, context=ctx
                )
                if applied and applied.marketing_results:
                    result = AgentResult.ok(applied.marketing_results[0])
            data = result.data
            return {
                "success": result.success,
                "dispatched": data.dispatched if data else False,
                "body": data.body if data else None,
            }

        tools.append(
            McpTool(
                name="marketing.thank_you",
                description="Send a thank-you message to a customer",
                input_schema={
                    "type": "object",
                    "required": ["shop_id"],
                    "properties": {
                        "shop_id": {"type": "string", "format": "uuid"},
                        "customer_id": {"type": "string", "format": "uuid"},
                        "channel": {"type": "string"},
                        "name": {"type": "string"},
                        "shop": {"type": "string"},
                    },
                },
                handler=send_thank_you,
                agent="marketing",
                tags=["marketing"],
            )
        )

    return tools
