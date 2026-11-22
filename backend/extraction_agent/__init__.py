"""
Financial Extraction Agent package.

Extracts financial metrics, ratios, and revenue trends from documents that
have already been parsed by the Document Agent's text extractor.

Public API:
    extract_financials(file_path, document_id) -> ExtractionResult
"""

from .agent import extract_financials
from .models import ExtractionResult, FinancialMetric, FinancialRatios, RevenueTrend

__all__ = [
    "extract_financials",
    "ExtractionResult",
    "FinancialMetric",
    "FinancialRatios",
    "RevenueTrend",
]
