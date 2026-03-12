"""Schema Loader: loads field constraints and canonical output field names."""
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SchemaLoader:
    """Loads and manages field constraints and canonical output schema."""

    def __init__(self, schema_path: str = "config/field_constraints.json"):
        self.schema_path = Path(schema_path)
        self.schema: List[Dict[str, Any]] = []
        self.field_index: Dict[str, Dict[str, Any]] = {}
        self._constraints_by_canonical: Dict[str, Dict[str, Any]] = {}
        self._canonical_fields: List[str] = []
        self.load_schema()
        self._validate_startup()

    def load_schema(self) -> None:
        """Load schema JSON file."""
        try:
            with open(self.schema_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, list):
                raise ValueError("field_constraints.json must contain a JSON list")
            self.schema = [row for row in loaded if isinstance(row, dict)]

            for field in self.schema:
                field_name = (
                    field.get("field_name")
                    or field.get("validator_name")
                    or field.get("Validator")
                    or field.get("column_name")
                )
                if isinstance(field_name, str) and field_name.strip():
                    self.field_index[field_name.strip()] = field

            self._canonical_fields = self._build_canonical_fields()
            self._constraints_by_canonical = self._build_constraints_by_canonical()

            logger.info("Loaded %d constraint rows from %s", len(self.schema), self.schema_path)
        except FileNotFoundError:
            logger.error("Schema file not found: %s", self.schema_path)
            raise
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in schema file: %s", e)
            raise

    def _to_snake(self, text: str) -> str:
        t = (text or "").strip().lower()
        t = t.replace("&", " and ")
        t = t.replace("%", " percentage ")
        t = re.sub(r"[()/\\'`.,:+-]+", " ", t)
        t = re.sub(r"\s+", "_", t).strip("_")
        t = re.sub(r"_+", "_", t)
        return t

    def _build_canonical_fields(self) -> List[str]:
        """Map all constraint rows to canonical JSON keys."""
        explicit_aliases = {
            "company_name": "name",
            "short_name": "short_name",
            "logo": "logo_url",
            "year_of_incorporation": "incorporation_year",
            "overview_of_the_company": "overview_text",
            "company_headquarters": "headquarters_address",
            "countries_operating_in": "operating_countries",
            "number_of_offices_beyond_hq": "office_count",
            "office_locations": "office_locations",
            "number_of_employees": "employee_size",
            "contact_person_name": "contact_person_name",
            "contact_person_title": "contact_person_title",
            "contact_person_email": "contact_person_email",
            "contact_person_phone_number": "contact_person_phone",
        }

        fields: List[str] = []
        seen: set[str] = set()
        for row in self.schema:
            raw_name = (
                row.get("field_name")
                or row.get("validator_name")
                or row.get("Validator")
                or row.get("column_name")
                or ""
            )
            slug = self._to_snake(str(raw_name))
            if not slug:
                continue
            key = explicit_aliases.get(slug, slug)
            if key not in seen:
                seen.add(key)
                fields.append(key)
        return fields

    def _build_constraints_by_canonical(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        canonical = set(self._canonical_fields)
        for row in self.schema:
            raw_name = (
                row.get("field_name")
                or row.get("validator_name")
                or row.get("Validator")
                or row.get("column_name")
                or ""
            )
            key = self._to_snake(str(raw_name))
            # Keep the same aliases as _build_canonical_fields.
            key = {
                "company_name": "name",
                "logo": "logo_url",
                "year_of_incorporation": "incorporation_year",
                "overview_of_the_company": "overview_text",
                "company_headquarters": "headquarters_address",
                "countries_operating_in": "operating_countries",
                "number_of_offices_beyond_hq": "office_count",
                "number_of_employees": "employee_size",
                "contact_person_phone_number": "contact_person_phone",
            }.get(key, key)
            if key and key in canonical:
                out[key] = row
        return out

    def _validate_startup(self) -> None:
        """Fail fast if canonical field contract is not exact."""
        if not self._canonical_fields:
            raise ValueError("Canonical field contract is empty")

        if len(set(self._canonical_fields)) != len(self._canonical_fields):
            raise ValueError("Canonical field contract contains duplicate field names")

    def get_all_field_names(self) -> List[str]:
        """Return canonical field names used by prompt and validator."""
        return list(self._canonical_fields)

    def get_expected_field_count(self) -> int:
        """Return expected canonical field count."""
        return len(self._canonical_fields)

    def get_field(self, field_name: str) -> Optional[Dict[str, Any]]:
        # Prefer canonical key lookup first, then raw index fallback.
        if field_name in self._constraints_by_canonical:
            return self._constraints_by_canonical[field_name]
        return self.field_index.get(field_name)

    def get_all_fields(self) -> List[Dict[str, Any]]:
        return self.schema

    def get_required_fields(self) -> List[str]:
        # All canonical fields are required for complete output.
        return list(self._canonical_fields)

    def get_field_constraints(self, field_name: str) -> Dict[str, Any]:
        field = self.get_field(field_name)
        return field if field else {}

    def get_schema_summary(self) -> Dict[str, Any]:
        required_fields = self.get_required_fields()
        return {
            "total_fields": len(self._canonical_fields),
            "required_fields": len(required_fields),
            "nullable_fields": len(self._canonical_fields) - len(required_fields),
            "constraints_rows": len(self.schema),
        }

    def validate_field_value(self, field_name: str, value: Any) -> tuple[bool, Optional[str]]:
        if field_name not in self._canonical_fields:
            return False, f"Field '{field_name}' is not in canonical schema"

        field = self.get_field(field_name)
        if not field:
            return True, None

        nullability = str(field.get("nullability", "")).strip().lower()
        if value is None and nullability in {"not null", "false", "required"}:
            return False, f"Field '{field_name}' cannot be null"

        return True, None
