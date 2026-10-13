"""What the site receives from the reading: a SUGGESTION, never a decision.

Every field is optional (the model may not find it) and carries how sure the reading is. The text of
the receipt is not returned: it may hold a CPF, a card number or a name.
"""

import datetime as dt

from pydantic import BaseModel, Field


class FieldConfidence(BaseModel):
    amount: float = Field(ge=0, le=1)
    date: float = Field(ge=0, le=1)
    vendor: float = Field(ge=0, le=1)
    document: float = Field(ge=0, le=1)


class OcrSuggestion(BaseModel):
    amount_cents: int | None
    occurred_on: dt.date | None
    vendor: str | None
    document_number: str | None
    confidence: FieldConfidence
    model: str
    elapsed_ms: int


class OcrStatus(BaseModel):
    enabled: bool
