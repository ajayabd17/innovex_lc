"""Dynamic Pydantic validator based on field_constraints canonical schema."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model

from core.schema_loader import SchemaLoader


_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "config" / "field_constraints.json"
_SCHEMA = SchemaLoader(str(_SCHEMA_PATH))
OUTPUT_FIELD_NAMES = _SCHEMA.get_all_field_names()

# Preserve numeric type where downstream rules rely on it.
INTEGER_FIELDS = {"incorporation_year"}


def _build_company_model():
    fields: Dict[str, tuple[type, Any]] = {}
    for field_name in OUTPUT_FIELD_NAMES:
        if field_name in INTEGER_FIELDS:
            fields[field_name] = (int, ...)
        else:
            fields[field_name] = (Any, ...)
    return create_model(
        "CompanyData",
        __config__=ConfigDict(validate_assignment=True, str_strip_whitespace=True, extra="forbid"),
        company_id=(Optional[int], None),
        **fields,
    )


CompanyData = _build_company_model()


class ValidationReport(BaseModel):
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    validated_fields: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


def validate_exact_keys(json_data: Dict[str, Any]) -> None:
    if not isinstance(json_data, dict):
        raise ValueError(f"Payload must be a dictionary, got {type(json_data).__name__}")

    payload_keys = set(json_data.keys())
    payload_keys.discard("company_id")
    expected_keys = set(OUTPUT_FIELD_NAMES)

    missing = sorted(expected_keys - payload_keys)
    extra = sorted(payload_keys - expected_keys)
    if missing or extra:
        parts: List[str] = []
        if missing:
            parts.append(f"missing={missing[:10]} (count={len(missing)})")
        if extra:
            parts.append(f"extra={extra[:10]} (count={len(extra)})")
        raise ValueError(
            f"Exact {len(OUTPUT_FIELD_NAMES)}-field contract violation: " + "; ".join(parts)
        )


def normalize_for_validation(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize common LLM drifts before strict validation."""
    normalized = dict(data)

    for field_name, value in list(normalized.items()):
        if field_name == "company_id":
            continue
        if value is None:
            continue
        if field_name in INTEGER_FIELDS:
            if isinstance(value, str):
                text = value.strip()
                if text.isdigit():
                    normalized[field_name] = int(text)
            continue
        if isinstance(value, bool):
            normalized[field_name] = "Yes" if value else "No"
        elif isinstance(value, (int, float)):
            normalized[field_name] = str(value)
        elif isinstance(value, list):
            normalized[field_name] = "; ".join(str(v) for v in value)
        elif isinstance(value, dict):
            normalized[field_name] = str(value)
        elif not isinstance(value, str):
            normalized[field_name] = str(value)

    return normalized


def validate_output(json_data: Dict[str, Any]) -> CompanyData:
    try:
        validate_exact_keys(json_data)
        normalized = normalize_for_validation(json_data)
        return CompanyData(**normalized)
    except Exception as e:
        raise ValueError(f"Validation failed: {str(e)}")


def find_null_like_fields(
    payload: Dict[str, Any],
    required_fields: Optional[List[str]] = None,
    critical_fields: Optional[List[str]] = None,
) -> List[str]:
    if not isinstance(payload, dict):
        return []

    null_tokens = {"", "na", "n/a", "null", "none", "unknown", "not available", "-"}
    targets = set(required_fields or [])
    targets.update(critical_fields or [])
    if not targets:
        targets = set(OUTPUT_FIELD_NAMES)

    failed: List[str] = []
    for field_name in sorted(targets):
        if field_name not in payload:
            failed.append(field_name)
            continue
        value = payload.get(field_name)
        if value is None:
            failed.append(field_name)
            continue
        if isinstance(value, str) and value.strip().lower() in null_tokens:
            failed.append(field_name)
    return failed
