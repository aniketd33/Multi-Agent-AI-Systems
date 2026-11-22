"""
Data structures for the Financial Extraction Agent.

Following the same convention as backend/document_agent/models.py: plain
dataclasses with docstrings, no processing logic, None means "not found".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FinancialMetric:
    """One extracted financial value with its provenance.

    Attributes:
        value: The numeric value, or None if not found.
        unit: Currency / scale unit, e.g. "USD millions", "USD billions".
        fiscal_period: Period the value refers to, e.g. "FY2024", "Q3 2024".
        page_number: 1-based page where the value was found, or None.
        raw_text: The text snippet surrounding the match, for auditability.
    """

    value: Optional[float] = None
    unit: Optional[str] = None
    fiscal_period: Optional[str] = None
    page_number: Optional[int] = None
    raw_text: Optional[str] = None


@dataclass
class FinancialRatios:
    """Ratios computed from extracted metrics. None when inputs are missing.

    Attributes:
        profit_margin: net_profit / revenue (as a fraction, e.g. 0.15 = 15%).
        current_ratio: current_assets / current_liabilities.
        debt_to_equity: total_liabilities / shareholders_equity.
    """

    profit_margin: Optional[float] = None
    current_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None


@dataclass
class RevenueTrend:
    """Trend analysis when revenue is available for multiple periods.

    Attributes:
        periods: List of fiscal period labels, chronologically sorted.
        values: Corresponding revenue values, same order as periods.
        direction: "increasing", "decreasing", or "stable".
        percentage_change: Overall change from first to last period, as a
            percentage (e.g. 12.5 means +12.5%). None if fewer than 2 periods.
    """

    periods: List[str] = field(default_factory=list)
    values: List[float] = field(default_factory=list)
    direction: Optional[str] = None
    percentage_change: Optional[float] = None


@dataclass
class ExtractionResult:
    """Structured result returned by extract_financials().

    All metric fields are lists because a document may contain multiple
    fiscal periods. When a metric is not found at all, the list is empty.

    Attributes:
        document_id: The document ID passed by the caller.
        company_name: Company name if identified, else None.
        revenue: List of FinancialMetric for each period found.
        expenses: Same structure.
        net_profit: Same structure.
        total_assets: Same structure.
        liabilities: Same structure.
        ebitda: Same structure.
        ratios: Computed ratios (None fields where inputs are missing).
        revenue_trend: Trend analysis, or None if fewer than 2 periods.
        extraction_errors: Non-fatal warnings (e.g. ambiguous matches).
    """

    document_id: str = ""
    company_name: Optional[str] = None
    revenue: List[FinancialMetric] = field(default_factory=list)
    expenses: List[FinancialMetric] = field(default_factory=list)
    net_profit: List[FinancialMetric] = field(default_factory=list)
    total_assets: List[FinancialMetric] = field(default_factory=list)
    liabilities: List[FinancialMetric] = field(default_factory=list)
    ebitda: List[FinancialMetric] = field(default_factory=list)
    ratios: FinancialRatios = field(default_factory=FinancialRatios)
    revenue_trend: Optional[RevenueTrend] = None
    extraction_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON response or DB storage."""
        import dataclasses

        def _serialise(obj):
            if dataclasses.is_dataclass(obj):
                return {
                    k: _serialise(v) for k, v in dataclasses.asdict(obj).items()
                }
            if isinstance(obj, list):
                return [_serialise(item) for item in obj]
            return obj

        return _serialise(self)
