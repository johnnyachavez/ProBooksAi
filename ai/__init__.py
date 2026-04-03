"""AI extraction and categorization module for ProBooks+ai."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractionResult:
    """Structured fields extracted from a document by the AI."""

    vendor: Optional[str] = None
    doc_type: Optional[str] = None       # invoice / bill / receipt / other
    invoice_number: Optional[str] = None
    doc_date: Optional[str] = None       # ISO format YYYY-MM-DD
    due_date: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    currency: str = "USD"
    notes: Optional[str] = None
    line_items: list = field(default_factory=list)  # [{"description": ..., "qty": ..., "unit_price": ..., "amount": ...}]
    confidence: float = 0.0             # 0.0 – 1.0
    raw_response: Optional[str] = None  # raw JSON string from the AI
    error: Optional[str] = None         # set if extraction failed


@dataclass
class CategorySuggestions:
    """COA categorisation suggestions returned by the AI."""

    coa_account: Optional[str] = None       # e.g. "6100 – Rent Expense"
    coa_account_number: Optional[str] = None
    tax_category: Optional[str] = None     # e.g. "Business Expense"
    confidence: float = 0.0
    rationale: Optional[str] = None
    alternatives: list = field(default_factory=list)  # [{"account": ..., "confidence": ...}]
    error: Optional[str] = None
