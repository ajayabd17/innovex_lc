import json
import os
from pathlib import Path

from validators.event_detector import detect_event
from validators.condition_checker import check_condition


BASE_DIR = Path(__file__).parent.parent


# --------------------------------------------------
# RULE LOADING
# --------------------------------------------------

def load_rules(rule_files=None):
    """
    Load ALL rule JSON files from the /rules directory.
    Returns a flat list of rules.
    """
    rules_dir = BASE_DIR / "rules"
    all_rules = []
    requested = rule_files
    if requested is None:
        env_files = os.getenv("RULE_FILES", "").strip()
        if env_files:
            requested = [f.strip() for f in env_files.split(",") if f.strip()]

    if requested:
        for name in requested:
            rule_file = rules_dir / name
            if not rule_file.exists():
                raise FileNotFoundError(f"Requested rule file not found: {rule_file}")
            with open(rule_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                all_rules.extend(data.get("rules", []))
    else:
        for rule_file in rules_dir.glob("*.json"):
            with open(rule_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                all_rules.extend(data.get("rules", []))

    return all_rules


# --------------------------------------------------
# COMPANY LOADING (for sample JSON testing)
# --------------------------------------------------

import csv as _csv


# Column mapping: CSV header → rule field name (mirrors validate_csv.py)
_CSV_COLUMN_MAP = {
    "name": "company_name",
    "tech_adoption_rating": "industry_benchmark_technology_adoption_rating",
    "incorporation_year": "year_of_incorporation",
    "headquarters_address": "headquarters_address",
    "category": "business_type",
    "industry": "industry",
    "website_url": "website",
    "operating_countries": "operating_countries",
    "annual_revenue": "annual_revenue",
    "regulatory_status": "regulatory_status",
    "linkedin_url": "linkedin_url",
    "short_name": "short_name",
    "focus_sectors": "focus_sectors",
    "employee_size": "employee_size",
    "recent_funding_rounds": "recent_funding_rounds",
    "key_investors": "key_investors",
    "brand_sentiment_score": "brand_sentiment_score",
    "glassdoor_rating": "glassdoor_rating",
    "net_promoter_score": "net_promoter_score",
    "customer_concentration_risk": "customer_concentration_risk",
    "geopolitical_risks": "geopolitical_risks",
    "burn_rate": "burn_rate",
}


def load_companies():
    """
    Load companies from the real CSV dataset.
    Uses the same column mapping as validate_csv.py.
    """
    csv_path = BASE_DIR / "Company Master(Flat Companies Data).csv"

    companies = []
    with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = _csv.DictReader(f)
        for row in reader:
            normalized = {}
            for k, v in row.items():
                mapped_key = _CSV_COLUMN_MAP.get(k, k)
                normalized[mapped_key] = v if v != "" else None
            companies.append(normalized)

    return companies


def normalize_company_for_rules(company: dict) -> dict:
    """
    Normalize generated 10-field JSON into rule-engine aliases.
    Keeps original keys and adds mapped aliases where needed.
    """
    normalized = dict(company or {})
    alias_map = {
        "name": "company_name",
        "category": "business_type",
        "website_url": "website",
        "incorporation_year": "year_of_incorporation",
        "tech_adoption_rating": "industry_benchmark_technology_adoption_rating",
    }
    for src, dst in alias_map.items():
        if dst not in normalized:
            normalized[dst] = normalized.get(src)
    return normalized



# --------------------------------------------------
# HELPER → SAFE COMPANY NAME EXTRACTION
# --------------------------------------------------

def get_company_name(company: dict) -> str:
    """
    Extract company name safely from different schemas.
    """
    return (
        company.get("name")
        or company.get("company_name")
        or company.get("company")
        or "UNKNOWN_COMPANY"
    )


# --------------------------------------------------
# CORE EVALUATION LOGIC
# --------------------------------------------------

def evaluate_company(company: dict, rules: list) -> dict:
    """
    Evaluate all applicable rules (event-based + always rules)
    """

    company_name = (
        company.get("company_name")
        or company.get("name")
        or "Unknown Company"
    )

    event = detect_event(company)

    # Match rules:
    matched_rules = [
        r for r in rules
        if r.get("event") == event or r.get("event") == "always"
    ]

    rule_results = []
    overall_status = "PASS"

    for rule in matched_rules:
        failed_conditions = []

        for condition in rule["expected_conditions"]:
            if not check_condition(company, condition):
                failed_conditions.append(condition)

        status = "PASS" if not failed_conditions else rule["severity"]

        if status in ["FAIL", "CRITICAL"]:
            overall_status = status

        rule_results.append(
            {
                "rule_id": rule["id"],
                "description": rule.get("description", ""),
                "severity": rule.get("severity", "FAIL"),
                "status": status,
                "failed_conditions": failed_conditions,
            }
        )

    return {
        "company": company_name,
        "event": event,
        "rule_results": rule_results,
        "overall_status": overall_status,
    }
