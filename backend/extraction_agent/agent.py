"""
Financial Extraction Agent.

Reuses the Document Agent extract_text() to read a document, then applies
regex-based pattern matching to extract financial metrics, compute ratios, and
identify revenue trends across multiple fiscal periods.

Public API:
    extract_financials(file_path, document_id) -> ExtractionResult
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from backend.document_agent.extractors import extract_text
from backend.document_agent.models import PageText

from .models import (
    ExtractionResult,
    FinancialMetric,
    FinancialRatios,
    RevenueTrend,
)

logger = logging.getLogger(__name__)

# ===========================================================================
# REGEX PATTERNS  (plain raw strings)
# ===========================================================================

# Number: 1,234.56 or (1,234.56) [negative in finance notation]
_NUMBER = r'[\(]?\d[\d,]*\.?\d*[\)]?'
_SCALE  = r'(?:\s*(?:billion|million|thousand|b|bn|m|mm|k))?'

# Fiscal period patterns
_PERIOD_PATTERNS = [
    re.compile(r'(?:Fiscal\s+Year\s+|FY\s*)\s*(\d{4})', re.IGNORECASE),
    re.compile(r'Q[1-4]\s*(?:FY\s*)?(\d{4})', re.IGNORECASE),
    re.compile(r'Year\s+Ended\s+\w+\s+\d+,?\s*(\d{4})', re.IGNORECASE),
]
_FY_STANDALONE = re.compile(r'\b(20\d{2})\b')

# Unit detection patterns
_UNIT_PATTERNS = [
    (re.compile(r'\bUSD\b|\bUS\$?\b|\$\s*\d', re.IGNORECASE), 'USD'),
    (re.compile(r'\bEUR\b|€', re.IGNORECASE), 'EUR'),
    (re.compile(r'\bGBP\b|£', re.IGNORECASE), 'GBP'),
    (re.compile(r'\bINR\b|\bRs\.?\b|₹', re.IGNORECASE), 'INR'),
    (re.compile(r'\b(billion|bn)\b', re.IGNORECASE), 'billions'),
    (re.compile(r'\b(million|mm)\b', re.IGNORECASE), 'millions'),
    (re.compile(r'\b(thousand|k)\b', re.IGNORECASE), 'thousands'),
]

# Optional currency prefix between label and number
_CUR = r'(?:US?\$?|\$)?\s*'

def _mk_pattern(label):
    # label + whitespace/colon separator + optional currency + number + scale
    return re.compile(label + r'\s*[:\s]\s*' + _CUR + _NUMBER + _SCALE, re.IGNORECASE)

_METRIC_PATTERNS = {
    "revenue": [
        _mk_pattern(r'(?:total\s+)?revenue[s]?'),
        _mk_pattern(r'revenue\s+from\s+operations'),
        _mk_pattern(r'(?:net\s+)?sales'),
    ],
    "expenses": [
        _mk_pattern(r'(?:total\s+)?(?:operating\s+)?expenses?'),
        _mk_pattern(r'cost\s+of\s+(?:goods|services|revenue)[/\\w]*'),
    ],
    "net_profit": [
        _mk_pattern(r'net\s+(?:profit|income|earnings)'),
        _mk_pattern(r'profit\s+(?:after|for\s+the)\s+(?:tax|year)'),
        _mk_pattern(r'profit\s+after\s+tax'),
    ],
    "total_assets": [
        _mk_pattern(r'total\s+assets'),
    ],
    "liabilities": [
        _mk_pattern(r'(?:total\s+)?liabilities?'),
    ],
    "ebitda": [
        _mk_pattern(r'EBITDA'),
        _mk_pattern(r'earnings?\s+before\s+interest\s+taxes?\s+depreciation\s+and\s+amortization'),
    ],
}

# Company name patterns
_COMPANY_PATTERNS = [
    re.compile(r'(?:Company\s+Name|Registrant\s+Name|Name\s+of\s+Company)\s*[:\s]\s*(.+?)(?:\n|$)', re.IGNORECASE),
    re.compile(r'(?:^|\n)\s*([A-Z][A-Za-z0-9&.,\s]{2,60}(?:Inc\.?|Corp\.?|Corporation|Company|Ltd\.?|Limited|LLC|SA|AG|NV|B\.V\.))\b', re.MULTILINE),
]

# ===========================================================================
# PARSING HELPERS
# ===========================================================================

def _parse_number(raw):
    """Parse a number string like 1,234.56 or (1,234.56) into a float."""
    s = raw.strip().replace(",", "")
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    s = re.sub(r"[$\u20ac\u00a3\u20b9]", "", s)
    s = re.sub(
        r"\b(billion|million|thousand|bn|b|mm|m|k|USD|EUR|GBP|INR|Rs\.?)\b",
        "", s, flags=re.IGNORECASE,
    )
    s = s.strip()
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return None


def _detect_scale_multiplier(text):
    """Return the numeric multiplier implied by a scale word."""
    lower = text.lower()
    if re.search(r"\b(billion|bn|b)\b", lower):
        return 1e9
    if re.search(r"\b(million|mm)\b", lower):
        return 1e6
    if re.search(r"\b(thousand|k)\b", lower):
        return 1e3
    return 1.0


def _detect_fiscal_period(text):
    """Scan text and return the first fiscal period found, or None."""
    for pat in _PERIOD_PATTERNS:
        m = pat.search(text)
        if m:
            groups = [g for g in m.groups() if g]
            if groups:
                return groups[0] if len(groups) == 1 else " ".join(groups)
    m = re.search(_FY_STANDALONE, text)
    if m:
        return m.group(1)
    return None


def _detect_unit(text):
    """Detect currency and scale from a text snippet."""
    currency = None
    scale = None
    for pat, label in _UNIT_PATTERNS:
        if pat.search(text):
            if label in ("USD", "EUR", "GBP", "INR"):
                currency = label
            else:
                scale = label
    if currency and scale:
        return "{} {}".format(currency, scale)
    if currency:
        return currency
    if scale:
        return scale
    return None


_EXPENSE_EXCLUSIONS = re.compile(
    r"income\s+tax|tax\s+expense|deferred\s+tax",
    re.IGNORECASE,
)


def _extract_metric_from_line(line, page_number, field_name, fiscal_period_hint, unit_hint=None):
    """Try to extract one metric from a single line of text."""
    for pat in _METRIC_PATTERNS.get(field_name, []):
        m = pat.search(line)
        if not m:
            continue
        if field_name == "expenses" and _EXPENSE_EXCLUSIONS.search(line):
            continue
        raw_number = m.group(0)
        num_match = re.search(_NUMBER, raw_number)
        if not num_match:
            continue
        value = _parse_number(num_match.group(0))
        if value is None:
            continue
        scale = _detect_scale_multiplier(raw_number)
        value = value * scale
        unit = _detect_unit(line) or unit_hint
        period = _detect_fiscal_period(line) or fiscal_period_hint
        snippet = line.strip()[:200]
        return FinancialMetric(
            value=value, unit=unit, fiscal_period=period,
            page_number=page_number, raw_text=snippet,
        )
    return None


def _extract_company_name(pages):
    """Try to identify the company name from the first few pages."""
    search_pages = pages[:3] if len(pages) >= 3 else pages
    for page in search_pages:
        for pat in _COMPANY_PATTERNS:
            m = pat.search(page.text)
            if m:
                name = m.group(1).strip().rstrip(".,;:")
                name = re.sub(r"(?i)^page\s+\d+\s*", "", name).strip()
                if 2 <= len(name) <= 100:
                    return name
    return None


def _extract_prior_year_metric(line, page_number, field_name, period_hint, unit_hint, current_metric):
    # When a table row holds two numbers side by side, extract the second (prior year).
    all_nums = re.findall(_NUMBER, line)
    if len(all_nums) < 2:
        return None
    val2 = _parse_number(all_nums[1])
    if val2 is None:
        return None
    val2 = val2 * _detect_scale_multiplier(line)
    prior_period = None
    all_years = _FY_STANDALONE.findall(line)
    if len(all_years) >= 2:
        prior_period = all_years[1]
    elif current_metric.fiscal_period and _FY_STANDALONE.match(current_metric.fiscal_period):
        try:
            prior_period = str(int(current_metric.fiscal_period) - 1)
        except ValueError:
            pass
    if prior_period is None:
        prior_period = period_hint
    return FinancialMetric(
        value=val2,
        unit=_detect_unit(line) or unit_hint,
        fiscal_period=prior_period,
        page_number=page_number,
        raw_text=line.strip()[:200],
    )


# ===========================================================================
# RATIO COMPUTATION
# ===========================================================================

def _compute_ratios(revenue, net_profit, total_assets, liabilities):
    """Compute financial ratios. None for any ratio whose inputs are missing."""
    ratios = FinancialRatios()
    if net_profit and revenue and revenue[0].value and net_profit[0].value:
        if revenue[0].value != 0:
            ratios.profit_margin = round(net_profit[0].value / revenue[0].value, 4)
    if total_assets and liabilities and total_assets[0].value and liabilities[0].value:
        if liabilities[0].value != 0 and total_assets[0].value != liabilities[0].value:
            ratios.debt_to_equity = round(
                liabilities[0].value / (total_assets[0].value - liabilities[0].value), 4
            )
    return ratios


# ===========================================================================
# REVENUE TREND
# ===========================================================================

def _analyse_revenue_trend(revenue_metrics):
    """Identify revenue trend when multiple fiscal periods are available."""
    valid = [m for m in revenue_metrics if m.value is not None and m.fiscal_period is not None]
    if len(valid) < 2:
        return None
    valid.sort(key=lambda m: m.fiscal_period)
    periods = [m.fiscal_period for m in valid]
    values = [m.value for m in valid if m.value is not None]
    if len(values) < 2:
        return None
    first, last = values[0], values[-1]
    pct_change = None if first == 0 else round(((last - first) / abs(first)) * 100, 2)
    if pct_change is None:
        direction = "unknown"
    elif pct_change > 1:
        direction = "increasing"
    elif pct_change < -1:
        direction = "decreasing"
    else:
        direction = "stable"
    return RevenueTrend(
        periods=periods, values=values,
        direction=direction, percentage_change=pct_change,
    )


# ===========================================================================
# MAIN EXTRACTION FUNCTION
# ===========================================================================

def extract_financials(file_path, document_id=""):
    """Extract financial metrics from a document.

    Reuses the Document Agent extract_text() to read the file, then applies
    regex-based pattern matching to find financial values on each page.

    Args:
        file_path: Path to a PDF, DOCX or TXT file on disk.
        document_id: Unique document ID for traceability.

    Returns:
        ExtractionResult with all found metrics, computed ratios, and
        revenue trend. Missing values are None or empty lists, never invented.

    Raises:
        Inherits exceptions from extract_text(): MissingFileError,
        EmptyDocumentError, ExtractionError, UnsupportedFormatError.
    """
    path = Path(file_path)
    logger.info("Financial extraction starting for %s (document_id=%s)", path.name, document_id)

    pages = extract_text(path)
    company_name = _extract_company_name(pages)

    collected = {
        "revenue": [], "expenses": [], "net_profit": [],
        "total_assets": [], "liabilities": [], "ebitda": [],
    }
    errors = []

    for page in pages:
        page_num = page.page_number
        period_hint = _detect_fiscal_period(page.text[:500])
        unit_hint = _detect_unit(page.text[:600])
        lines = page.text.split("\n")
        # Build pairs: (label_line, value_line) for table layouts where
        # pypdf puts the metric label and its value on consecutive lines.
        # _HEADER_LINE matches bare year/column-header lines that should
        # not be used as the start of a 3-line join.
        _HEADER_LINE = re.compile(
            r"^(?:FY\s*\d{4}|Q[1-4]\s*\d{4}|Particulars|Amount|FY)$",
            re.IGNORECASE,
        )
        pairs = []
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped:
                pairs.append(stripped)
                n1 = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
                n2 = lines[idx + 2].strip() if idx + 2 < len(lines) else ""
                if n1:
                    pairs.append(stripped + " " + n1)
                # Only build 3-line triple when the anchor is a metric label,
                # not a bare year header or a bare number from the previous row.
                _IS_BARE_NUM = re.compile(r'^[\(]?[\d][\d,]*\.?[\d]*[\)]?$')
                if n1 and n2 and not _HEADER_LINE.match(stripped) and not _IS_BARE_NUM.match(stripped):
                    pairs.append(stripped + " " + n1 + " " + n2)
        seen_in_page = set()
        for line_stripped in pairs:
            if len(line_stripped) < 5:
                continue
            for field_name in collected:
                metric = _extract_metric_from_line(
                    line_stripped, page_num, field_name, period_hint, unit_hint,
                )
                if metric is not None:
                    dedup_key = (field_name, round(metric.value or 0, 1), metric.fiscal_period)
                    if dedup_key not in seen_in_page:
                        seen_in_page.add(dedup_key)
                        is_dup = any(
                            m.value == metric.value and m.fiscal_period == metric.fiscal_period
                            for m in collected[field_name]
                        )
                        if not is_dup:
                            collected[field_name].append(metric)
                    # Always attempt prior-year extraction -- the combined line may
                    # contain a second number even if the current-year value was
                    # already recorded from an earlier pair.
                    m2 = _extract_prior_year_metric(line_stripped, page_num, field_name, period_hint, unit_hint, metric)
                    if m2 is not None:
                        m2_key = (field_name, round(m2.value or 0, 1), m2.fiscal_period)
                        if m2_key not in seen_in_page and not any(x.value == m2.value and x.fiscal_period == m2.fiscal_period for x in collected[field_name]):
                            seen_in_page.add(m2_key)
                            collected[field_name].append(m2)

    ratios = _compute_ratios(
        collected["revenue"], collected["net_profit"],
        collected["total_assets"], collected["liabilities"],
    )
    revenue_trend = _analyse_revenue_trend(collected["revenue"])

    result = ExtractionResult(
        document_id=document_id,
        company_name=company_name,
        revenue=collected["revenue"],
        expenses=collected["expenses"],
        net_profit=collected["net_profit"],
        total_assets=collected["total_assets"],
        liabilities=collected["liabilities"],
        ebitda=collected["ebitda"],
        ratios=ratios,
        revenue_trend=revenue_trend,
        extraction_errors=errors,
    )

    logger.info(
        "Financial extraction complete for %s: company=%s, revenue=%d period(s), ebitda=%d period(s), trend=%s",
        path.name, company_name or "unknown",
        len(result.revenue), len(result.ebitda),
        revenue_trend.direction if revenue_trend else "N/A",
    )
    return result
