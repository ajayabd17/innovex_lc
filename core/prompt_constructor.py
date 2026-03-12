"""
Prompt Constructor: Builds structured prompts for LLM generation.
Ensures consistent, deterministic prompt formatting across all LLM providers.
"""
import json
import logging
from typing import Any, Dict, List

from core.schema_loader import SchemaLoader

logger = logging.getLogger(__name__)


class PromptConstructor:
    """Constructs structured generation prompts."""

    def __init__(self, schema_loader: SchemaLoader):
        self.schema_loader = schema_loader

    def build_generation_prompt(self, company_name: str) -> str:
        field_names = self.schema_loader.get_all_field_names()
        return self.build_generation_prompt_for_fields(company_name, field_names)

    def build_generation_prompt_for_fields(self, company_name: str, field_names: List[str]) -> str:
        json_template = {field_name: None for field_name in field_names}

        prompt = f"""You are an expert company research analyst. Generate structured data for one company.

Company Name: {company_name}

=== CRITICAL REQUIREMENTS ===
1. Return ONLY valid JSON (no markdown, no commentary)
2. Include ALL {len(field_names)} fields listed below
3. Use null for unknown values
4. Keep values concise and factual
5. For narrative fields, keep to 20 words maximum
6. Output must be one JSON object with no trailing text
7. Follow this style reference:
   - Company names as official legal names (e.g., "Accenture plc")
   - Multi-value fields as semicolon-separated values
   - Financial fields with units/context (e.g., "$64.1B (FY2024)")
   - URLs must be fully qualified https links
   - Ratings as text like "4.1/5" and percentages like "3%"

=== ALL 10 REQUIRED FIELDS ===
{json.dumps(json_template, indent=2)}

=== INSTRUCTIONS ===
- Use actual data for {company_name}
- Keep exact field names and exact key count ({len(field_names)})
- Do not omit or add keys
- Do not include `company_id`
- Return only the complete JSON object

Begin your response with {{ and end with }}. No other text.
"""
        return prompt

    def build_repair_prompt_for_fields(
        self,
        company_name: str,
        failed_fields: List[str],
        current_payload: Dict[str, Any],
    ) -> str:
        """Build a targeted correction prompt for only the fields that failed validation."""
        failed_template = {field_name: current_payload.get(field_name) for field_name in failed_fields}
        return f"""You are fixing JSON field validation errors for company data.

Company Name: {company_name}

Return ONLY one valid JSON object containing EXACTLY these fields:
{json.dumps(failed_template, indent=2)}

Rules:
1. Keep exact field names; do not add extra keys
2. Correct data types/format so fields pass strict validation
3. Use null if unknown
4. Return only JSON with no markdown or extra text
"""

    def build_consolidation_prompt(
        self,
        company_name: str,
        three_outputs: Dict[str, Dict[str, Any]],
        comparisons: Dict[str, List[str]],
    ) -> str:
        available_models = [k for k, v in three_outputs.items() if isinstance(v, dict)]
        canonical_fields = self.schema_loader.get_all_field_names()
        model_count = len(available_models)

        # Compact per-field candidates to avoid token-limit failures on consolidation.
        # Keep content short but still informative for conflict resolution.
        candidates: Dict[str, Dict[str, Any]] = {}
        for field_name in canonical_fields:
            per_field: Dict[str, Any] = {}
            for model_name in available_models:
                value = three_outputs.get(model_name, {}).get(field_name)
                if isinstance(value, str) and len(value) > 220:
                    value = value[:220].rstrip() + "..."
                per_field[model_name] = value
            candidates[field_name] = per_field

        compact_candidates = json.dumps(candidates, ensure_ascii=True, separators=(",", ":"))

        return (
            f"You are an expert data reconciliation specialist. Consolidate {model_count} AI model outputs "
            f"into one authoritative 10-field dataset for {company_name}.\n\n"
            "Rules:\n"
            "1) Keep exact field keys only (no extra keys)\n"
            "2) Prefer values agreed by most models\n"
            "3) If conflict, choose most reliable factual value\n"
            "4) Use null only when all candidates are unknown/unreliable\n"
            "5) Return ONLY one valid JSON object\n\n"
            "Field candidates (field -> provider -> value):\n"
            f"{compact_candidates}\n\n"
            "Return ONLY the final consolidated JSON object with all 10 fields."
        )

    def _format_schema_summary(self) -> str:
        summary = self.schema_loader.get_schema_summary()
        return f"""Total Fields: {summary['total_fields']}
Required Fields: {summary['required_fields']}
Nullable Fields: {summary['nullable_fields']}

Categories:
{json.dumps(summary.get('categories', {}), indent=2)}
"""

    def _format_field_definitions(self) -> str:
        fields = self.schema_loader.get_all_fields()
        formatted = []

        for field in fields[:20]:
            field_name = field.get("Validator", "")
            if field_name:
                formatted.append(
                    f"""
Field: {field_name}
  Type: {field.get('data_type', 'N/A')}
  Nullable: {field.get('nullability', 'N/A')}
  Format: {field.get('format_constraints', 'N/A')}
  Validation: {field.get('validation_mode', 'N/A')}
"""
                )

        formatted.append("\n... (and 143+ more fields with similar structure)\n")
        return "\n".join(formatted)

    def _format_comparison_report(self, comparisons: Dict[str, List[str]]) -> str:
        report_lines = []
        for field_name, models_with_value in comparisons.items():
            report_lines.append(f"- {field_name}: {', '.join(models_with_value)} agree")
        return "\n".join(report_lines) if report_lines else "All fields match across models"

    def create_retry_prompt(
        self, company_name: str, previous_output: Dict[str, Any], validation_errors: List[str]
    ) -> str:
        prompt = f"""You are fixing an AI-generated dataset. A previous generation had validation errors.

Company Name: {company_name}

=== PREVIOUS OUTPUT ===
{json.dumps(previous_output, indent=2)}

=== VALIDATION ERRORS TO FIX ===
{json.dumps(validation_errors, indent=2)}

=== YOUR TASK ===
1. Analyze each error
2. Correct ONLY the problematic fields
3. Keep all other fields unchanged
4. Ensure corrections maintain cross-field consistency
5. Return the corrected complete JSON object

Requirements:
- Return ONLY valid JSON
- No commentary
- Fix ALL errors listed above
- Validate corrected fields against constraints

Corrected JSON output:
"""
        return prompt
