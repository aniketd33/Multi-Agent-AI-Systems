
"""
Rule-based Red Flag Agent for financial documents.

Scans extracted document text for auditor concerns, debt increases,
margin declines, and unusual financial patterns.
"""

import asyncio
import logging
import re
from typing import Dict, List

from backend.document_agent.extractors import extract_text
from backend.database.db import (
    save_red_flag_analysis,
)

logger = logging.getLogger(__name__)

# These patterns identify explicit risk statements, not generic mentions.
RULES = [
    {
        "category": "auditor_qualification",
        "severity": "critical",
        "title": "Qualified audit opinion",
        "pattern": r"\bqualified opinion\b|\bexcept for\b.{0,100}\bopinion\b",
        "explanation": "The auditor's wording may indicate a qualification in the audit opinion.",
        "recommendation": "Review the auditor's report and the specific basis for the qualification.",
    },
    {
        "category": "auditor_qualification",
        "severity": "critical",
        "title": "Adverse audit opinion",
        "pattern": r"\badverse opinion\b",
        "explanation": "An adverse opinion indicates that the financial statements may be materially misstated.",
        "recommendation": "Review the auditor's stated reasons and the affected financial statements.",
    },
    {
        "category": "auditor_qualification",
        "severity": "high",
        "title": "Disclaimer of opinion",
        "pattern": r"\bdisclaimer of opinion\b",
        "explanation": "The auditor may be unable to obtain sufficient appropriate audit evidence.",
        "recommendation": "Review the scope limitations and auditor's explanation.",
    },
    {
        "category": "audit_control",
        "severity": "high",
        "title": "Material weakness in internal controls",
        "pattern": r"\bmaterial weakness(?:es)?\b",
        "explanation": "The document refers to a material weakness in internal control.",
        "recommendation": "Review the affected controls and management's remediation plan.",
    },
    {
        "category": "going_concern",
        "severity": "critical",
        "title": "Going concern warning",
        "pattern": r"\bsubstantial doubt about.{0,80}going concern\b|\bgoing concern uncertainty\b",
        "explanation": "The wording indicates substantial uncertainty about the entity's ability to continue as a going concern.",
        "recommendation": "Review liquidity, cash-flow forecasts, debt maturities, and the auditor's disclosures.",
    },
    {
        "category": "financial_anomaly",
        "severity": "high",
        "title": "Financial restatement mentioned",
        "pattern": r"\b(restated|restatement of|restatement to)\b",
        "explanation": "The document refers to a financial restatement, which may indicate previously reported information was revised.",
        "recommendation": "Compare restated figures with previously reported figures and review the reason for the change.",
    },
    {
        "category": "financial_anomaly",
        "severity": "high",
        "title": "Debt covenant breach mentioned",
        "pattern": r"\b(covenant violation|breach of.{0,40}covenant|default under.{0,40}credit agreement)\b",
        "explanation": "The document refers to a possible debt covenant breach or credit agreement default.",
        "recommendation": "Review the relevant debt agreement, waiver status, and repayment obligations.",
    },
    {
        "category": "financial_anomaly",
        "severity": "medium",
        "title": "Significant impairment mentioned",
        "pattern": r"\b(significant impairment|impairment charge|impairment loss)\b",
        "explanation": "The document reports an impairment-related event that may affect asset values or earnings.",
        "recommendation": "Review the affected asset, impairment assumptions, and financial impact.",
    },
]

TREND_RULES = [
    {
        "category": "rising_debt",
        "severity": "high",
        "title": "Rising debt indicated",
        "metric_pattern": r"\b(debt|borrowings|loans payable|financial liabilities)\b",
        "trend_pattern": r"\b(increased|increase|rising|rose|higher|grew|growth)\b",
        "explanation": "The same passage mentions debt or borrowings together with an increase.",
        "recommendation": "Compare debt balances across reporting periods and review interest and repayment obligations.",
    },
    {
        "category": "falling_margins",
        "severity": "medium",
        "title": "Falling margin indicated",
        "metric_pattern": r"\b(gross margin|operating margin|profit margin|net margin)\b",
        "trend_pattern": r"\b(decreased|decrease|declined|decline|fell|lower|reduced|reduction)\b",
        "explanation": "The same passage mentions a profit margin together with a decline.",
        "recommendation": "Compare the margin across reporting periods and investigate revenue, cost, and expense changes.",
    },
]


def _add_finding(
    findings: List[Dict],
    seen: set,
    category: str,
    severity: str,
    title: str,
    explanation: str,
    recommendation: str,
    evidence: str,
    page_number,
):
    key = (category, title, page_number, evidence[:100])
    if key in seen:
        return

    seen.add(key)
    findings.append({
        "category": category,
        "severity": severity,
        "title": title,
        "explanation": explanation,
        "evidence": evidence[:700],
        "page_number": page_number,
        "recommended_follow_up": recommendation,
    })


def analyze_pages(pages: List) -> List[Dict]:
    """Analyze extracted pages and return evidence-backed findings."""
    findings = []
    seen = set()

    for page in pages:
        page_text = getattr(page, "text", "") or ""
        page_number = getattr(page, "page_number", None)

        for line in page_text.splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if len(line) < 12:
                continue

            for rule in RULES:
                if re.search(rule["pattern"], line, re.IGNORECASE):
                    _add_finding(
                        findings, seen,
                        rule["category"], rule["severity"], rule["title"],
                        rule["explanation"], rule["recommendation"],
                        line, page_number,
                    )

            for rule in TREND_RULES:
                if (
                    re.search(rule["metric_pattern"], line, re.IGNORECASE)
                    and re.search(rule["trend_pattern"], line, re.IGNORECASE)
                ):
                    _add_finding(
                        findings, seen,
                        rule["category"], rule["severity"], rule["title"],
                        rule["explanation"], rule["recommendation"],
                        line, page_number,
                    )

    return findings


async def run_red_flag_agent(
    file_path: str,
    document_id: str,
    filename: str,
) -> Dict:
    """
    Async agent entry point.

    OCR/text extraction is offloaded to a worker thread.
    Analysis orchestration and async database operations remain
    inside the FastAPI event loop.
    """
    await save_red_flag_analysis(
        document_id=document_id,
        status="running",
        findings=[],
        error=None,
    )

    try:
        pages = await asyncio.to_thread(extract_text, file_path)
        findings = analyze_pages(pages)

        summary = {
            "total_findings": len(findings),
            "critical": sum(f["severity"] == "critical" for f in findings),
            "high": sum(f["severity"] == "high" for f in findings),
            "medium": sum(f["severity"] == "medium" for f in findings),
            "low": sum(f["severity"] == "low" for f in findings),
        }

        await save_red_flag_analysis(
            document_id=document_id,
            status="completed",
            findings=findings,
            error=None,
        )

        logger.info(
            "[red-flag] Completed %s: %s finding(s)",
            filename,
            len(findings),
        )

        return {
            "document_id": document_id,
            "filename": filename,
            "status": "completed",
            "summary": summary,
            "findings": findings,
            "message": (
                "No rule-based red flags were detected."
                if not findings
                else "Red flag analysis completed."
            ),
        }

    except Exception as exc:
        logger.exception("[red-flag] Analysis failed for %s", filename)

        await save_red_flag_analysis(
            document_id=document_id,
            status="failed",
            findings=[],
            error=str(exc),
        )
        raise
