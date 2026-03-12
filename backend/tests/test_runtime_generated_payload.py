import json
import os
from pathlib import Path

from validators.pydantic_model import validate_output
from validators.rule_engine import evaluate_company, load_rules, normalize_company_for_rules


def _load_payload() -> dict:
    payload_path = os.getenv("GENERATED_PAYLOAD_PATH", "").strip()
    if not payload_path:
        raise AssertionError("GENERATED_PAYLOAD_PATH env var is required for runtime pytest gate")

    path = Path(payload_path)
    if not path.exists():
        raise AssertionError(f"Generated payload file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "company_json" in data and isinstance(data["company_json"], dict):
        return data["company_json"]
    if not isinstance(data, dict):
        raise AssertionError("Generated payload must be a JSON object")
    return data


def test_runtime_payload_passes_pydantic() -> None:
    payload = _load_payload()
    validate_output(payload)


def test_runtime_payload_passes_project_rules() -> None:
    payload = _load_payload()
    rules = load_rules(["project_runtime_rules.json"])
    result = evaluate_company(normalize_company_for_rules(payload), rules)
    assert result["overall_status"] == "PASS", f"Runtime rules failed: {result}"
