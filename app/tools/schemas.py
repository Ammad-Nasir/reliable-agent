from pydantic import BaseModel, Field, EmailStr
from typing import Literal, Optional

class LookupCustomerInput(BaseModel):
    customer_id: str = Field(
        ..., 
        description="The unique customer identifier (e.g., 'CUST-1001') or customer email."
    )

class LookupOrderInput(BaseModel):
    order_id: str = Field(
        ..., 
        description="The unique order identifier (e.g., 'ORD-8821')."
    )

class CalculateDelayCompensationInput(BaseModel):
    order_id: str = Field(
        ..., 
        description="The order ID for which delay compensation is being calculated."
    )
    delay_days: int = Field(
        ..., 
        ge=0, 
        description="Number of days the package has been delayed past promised delivery date."
    )
    customer_tier: Literal["Bronze", "Silver", "Gold", "VIP"] = Field(
        default="Bronze",
        description="Customer loyalty tier for tier-specific compensation bonuses."
    )

class IssueRefundInput(BaseModel):
    order_id: str = Field(
        ..., 
        description="The order ID to issue a refund against."
    )
    amount: float = Field(
        ..., 
        gt=0.0, 
        description="Monetary amount to refund in USD. Must be strictly positive."
    )
    reason: str = Field(
        ..., 
        min_length=5, 
        description="Auditable justification for the refund (minimum 5 characters)."
    )
    refund_method: Literal["ORIGINAL_PAYMENT", "STORE_CREDIT"] = Field(
        default="ORIGINAL_PAYMENT", 
        description="Destination payment method for the refunded amount."
    )

class SendEmailNotificationInput(BaseModel):
    customer_email: str = Field(
        ..., 
        description="Recipient email address."
    )
    subject: str = Field(
        ..., 
        min_length=3, 
        description="Subject line for the communication."
    )
    body: str = Field(
        ..., 
        min_length=10, 
        description="Body text of the email message."
    )
    template_type: Literal["APOLOGY", "REFUND_CONFIRMATION", "GENERAL_UPDATE", "VOUCHER"] = Field(
        default="GENERAL_UPDATE",
        description="Template style category for formatting."
    )

class FlagAccountFraudInput(BaseModel):
    customer_id: str = Field(
        ..., 
        description="The customer ID accused or suspected of abuse/fraud."
    )
    reason: str = Field(
        ..., 
        min_length=5, 
        description="Specific reason or evidence of fraudulent pattern."
    )
    action: Literal["FLAG_SUSPICIOUS", "FREEZE_ACCOUNT", "FORCE_PASSWORD_RESET"] = Field(
        default="FLAG_SUSPICIOUS",
        description="Action to apply. FREEZE_ACCOUNT carries high risk and requires human approval."
    )
