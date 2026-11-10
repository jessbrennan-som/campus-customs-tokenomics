"""Shape of the answer the vendor desk agent must return (PydanticAI validates it)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class VendorDecision(BaseModel):
    vendor: str = Field(description="Vendor name exactly as the document gives it, e.g. 'Blue Hen Apparel'.")
    sku: Optional[str] = Field(
        default=None,
        description="Campus Customs SKU (e.g. CC-HD-006). null if the document does not name one.",
    )
    unit_price: Optional[float] = Field(
        default=None,
        description="Quoted price per unit in US dollars. null if the document does not say (never guess).",
    )
    lead_time_days: Optional[int] = Field(
        default=None,
        description="Lead time as a number of days, as the document states it. null if not stated.",
    )
    minimum_order: Optional[int] = Field(
        default=None,
        description="Minimum order in units. null if not stated.",
    )
    decision: Literal["recommend", "do_not_recommend"] = Field(
        description="'recommend' only if the vendor is approved AND price, lead time and minimum order all pass the handbook checks."
    )
    reason: str = Field(
        description="ONE sentence naming the handbook check that decided it (approved vendor, price, lead time, or minimum order)."
    )
