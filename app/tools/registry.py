from typing import Dict, Any, Callable, Type
from pydantic import BaseModel
from app.config import settings
from app.tools.schemas import (
    LookupCustomerInput,
    LookupOrderInput,
    CalculateDelayCompensationInput,
    IssueRefundInput,
    SendEmailNotificationInput,
    FlagAccountFraudInput,
)
from app.tools.implementations import (
    lookup_customer,
    lookup_order,
    calculate_delay_compensation,
    issue_refund,
    send_email_notification,
    flag_account_fraud,
)

class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        schema: Type[BaseModel],
        func: Callable,
        is_risky: bool = False,
        risk_evaluator: Callable[[Dict[str, Any]], Tuple[bool, str]] = None
    ):
        self.name = name
        self.description = description
        self.schema = schema
        self.func = func
        self.is_risky = is_risky
        self.risk_evaluator = risk_evaluator or (lambda p: (is_risky, "High risk action requires human authorization."))

    def to_claude_tool(self) -> Dict[str, Any]:
        """Convert tool to Claude tool calling schema format."""
        schema_dict = self.schema.model_json_schema()
        # Clean schema for API
        properties = schema_dict.get("properties", {})
        required = schema_dict.get("required", [])
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }

def _refund_risk_evaluator(params: Dict[str, Any]) -> tuple[bool, str]:
    amount = float(params.get("amount", 0.0))
    if amount > settings.HIGH_RISK_REFUND_THRESHOLD:
        return (
            True, 
            f"Requested refund of ${amount:.2f} exceeds automatic approval limit of ${settings.HIGH_RISK_REFUND_THRESHOLD:.2f}."
        )
    return (False, "Standard refund within automatic limits.")

def _fraud_risk_evaluator(params: Dict[str, Any]) -> tuple[bool, str]:
    action = params.get("action", "FLAG_SUSPICIOUS")
    if action == "FREEZE_ACCOUNT":
        return (
            True,
            f"Action 'FREEZE_ACCOUNT' directly suspends customer access and requires managerial authorization."
        )
    return (False, "Standard security tagging within operational bounds.")

TOOL_REGISTRY: Dict[str, ToolDefinition] = {
    "lookup_customer": ToolDefinition(
        name="lookup_customer",
        description="Look up customer details, tier, lifetime spend, and fraud score by ID or email.",
        schema=LookupCustomerInput,
        func=lookup_customer,
        is_risky=False
    ),
    "lookup_order": ToolDefinition(
        name="lookup_order",
        description="Look up order details, items, delivery status, delay days, and tracking.",
        schema=LookupOrderInput,
        func=lookup_order,
        is_risky=False
    ),
    "calculate_delay_compensation": ToolDefinition(
        name="calculate_delay_compensation",
        description="Calculate policy-backed compensation voucher or credit for delayed packages.",
        schema=CalculateDelayCompensationInput,
        func=calculate_delay_compensation,
        is_risky=False
    ),
    "issue_refund": ToolDefinition(
        name="issue_refund",
        description=f"Issue a monetary refund for an order. Refunds over ${settings.HIGH_RISK_REFUND_THRESHOLD:.2f} require human supervisor approval.",
        schema=IssueRefundInput,
        func=issue_refund,
        is_risky=True,
        risk_evaluator=_refund_risk_evaluator
    ),
    "send_email_notification": ToolDefinition(
        name="send_email_notification",
        description="Send an email to a customer with resolution, apology, or confirmation.",
        schema=SendEmailNotificationInput,
        func=send_email_notification,
        is_risky=False
    ),
    "flag_account_fraud": ToolDefinition(
        name="flag_account_fraud",
        description="Flag an account for fraud or freeze account access. Account freezing requires human supervisor approval.",
        schema=FlagAccountFraudInput,
        func=flag_account_fraud,
        is_risky=True,
        risk_evaluator=_fraud_risk_evaluator
    )
}

def get_claude_tools():
    return [t.to_claude_tool() for t in TOOL_REGISTRY.values()]
