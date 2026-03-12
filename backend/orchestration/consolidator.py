"""
Consolidation orchestration with strict canonical field checks.
"""
import ast
import json
import logging
from typing import Any, Dict, Optional, Set

from core.field_comparator import FieldComparator
from core.prompt_constructor import PromptConstructor
from core.schema_loader import SchemaLoader
from llm.consolidation_client import get_consolidation_client

logger = logging.getLogger(__name__)


class Consolidator:
    """Reconciles and consolidates multiple LLM outputs."""

    def __init__(self, max_retries: int = 3, schema_loader: Optional[SchemaLoader] = None):
        self.consolidator_llm = get_consolidation_client()
        self.max_retries = max_retries
        self.field_comparator = FieldComparator()
        self.schema_loader = schema_loader or SchemaLoader()
        self.prompt_constructor = PromptConstructor(self.schema_loader)
        self.expected_fields: Set[str] = set(self.schema_loader.get_all_field_names())

    def consolidate(self, responses: Dict[str, Dict[str, Any]], company_name: str) -> Dict[str, Any]:
        self._validate_input_models(responses)

        comparison_results = self.field_comparator.compare(responses)
        consolidated = self._build_from_comparisons(comparison_results)

        logger.info(
            "Consolidation breakdown - unanimous=%d majority=%d conflicts=%d missing=%d",
            len(comparison_results["unanimous_fields"]),
            len(comparison_results["majority_fields"]),
            len(comparison_results["conflicting_fields"]),
            len(comparison_results["missing_fields"]),
        )

        consolidated = self._resolve_with_llm(
            responses=responses,
            comparison_results=comparison_results,
            company_name=company_name,
            initial_consolidated=consolidated,
        )

        self._validate_final_shape(consolidated)
        return consolidated

    def _validate_input_models(self, responses: Dict[str, Dict[str, Any]]) -> None:
        allowed = {"groq", "fireworks", "baseten"}
        provided = set(responses.keys())
        if not provided.issubset(allowed):
            raise ValueError(f"Consolidator received unknown models: {sorted(provided - allowed)}")
        if len(provided) < 2:
            raise ValueError("Consolidator requires at least 2 model outputs")

        for model_name, payload in responses.items():
            if not isinstance(payload, dict):
                raise ValueError(f"{model_name} payload must be dict, got {type(payload).__name__}")

    def _build_from_comparisons(self, comparison_results: Dict[str, Any]) -> Dict[str, Any]:
        consolidated = {}

        for field_name, value in comparison_results["unanimous_fields"].items():
            consolidated[field_name] = value

        for field_name, data in comparison_results["majority_fields"].items():
            consolidated[field_name] = data["value"]

        for field_name in comparison_results["conflicting_fields"]:
            value, _ = self.field_comparator.get_recommended_value(field_name)
            if value is not None:
                consolidated[field_name] = value

        for field_name in comparison_results["missing_fields"]:
            value, _ = self.field_comparator.get_recommended_value(field_name)
            if value is not None:
                consolidated[field_name] = value

        return consolidated

    def _resolve_with_llm(
        self,
        responses: Dict[str, Dict[str, Any]],
        comparison_results: Dict[str, Any],
        company_name: str,
        initial_consolidated: Dict[str, Any],
    ) -> Dict[str, Any]:
        last_error: Optional[str] = None
        for attempt in range(self.max_retries):
            try:
                prompt = self.prompt_constructor.build_consolidation_prompt(
                    company_name,
                    responses,
                    {k: list(v) for k, v in comparison_results["field_distribution"].items()},
                )
                response = self.consolidator_llm.invoke(prompt)
                llm_json = self._parse_json_response(response)

                merged = dict(initial_consolidated)
                merged.update(llm_json)

                self._validate_final_shape(merged)
                logger.info("Consolidation LLM succeeded on attempt %d", attempt + 1)
                return merged
            except Exception as e:
                last_error = str(e)
                logger.warning("Consolidation LLM attempt %d failed: %s", attempt + 1, e)
                if attempt < self.max_retries - 1:
                    try:
                        repair_prompt = self._build_consolidation_repair_prompt(
                            company_name=company_name,
                            responses=responses,
                            current=initial_consolidated,
                            error_text=last_error,
                        )
                        repair_response = self.consolidator_llm.invoke(repair_prompt)
                        repair_json = self._parse_json_response(repair_response)
                        merged = dict(initial_consolidated)
                        merged.update(repair_json)
                        self._validate_final_shape(merged)
                        logger.info("Consolidation LLM repair succeeded on attempt %d", attempt + 1)
                        return merged
                    except Exception as repair_error:
                        last_error = f"{last_error} | repair: {repair_error}"
                        logger.warning(
                            "Consolidation LLM repair attempt %d failed: %s",
                            attempt + 1,
                            repair_error,
                        )

        raise ValueError(
            f"Consolidation failed: unable to produce valid {len(self.expected_fields)}-field JSON after retries"
            + (f" | last_error={last_error}" if last_error else "")
        )

    def _validate_final_shape(self, payload: Dict[str, Any]) -> None:
        keys = set(payload.keys())
        missing = sorted(self.expected_fields - keys)
        extra = sorted(keys - self.expected_fields)
        if missing or extra:
            msg = []
            if missing:
                msg.append(f"missing={missing[:10]} (count={len(missing)})")
            if extra:
                msg.append(f"extra={extra[:10]} (count={len(extra)})")
            raise ValueError(
                f"Consolidated payload does not match canonical {len(self.expected_fields)}-field contract: "
                + "; ".join(msg)
            )

    def _parse_json_response(self, response: Any) -> Dict[str, Any]:
        response_text = response.content if hasattr(response, "content") else str(response)
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        cleaned = response_text.strip()

        # 1) direct strict JSON
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        # 2) extract first complete JSON object
        extracted = self._extract_json_object(cleaned)
        if extracted:
            try:
                data = json.loads(extracted)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
            try:
                data = ast.literal_eval(extracted)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        # 3) Python-dict-like fallback
        try:
            data = ast.literal_eval(cleaned)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        snippet = cleaned[:240].replace("\n", " ")
        raise ValueError(f"Consolidation response is not a JSON object. Raw snippet: {snippet}")

    def _extract_json_object(self, text: str) -> Optional[str]:
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        in_str = False
        escaped = False
        for idx, ch in enumerate(text[start:], start=start):
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
        return None

    def _build_consolidation_repair_prompt(
        self,
        company_name: str,
        responses: Dict[str, Dict[str, Any]],
        current: Dict[str, Any],
        error_text: str,
    ) -> str:
        required_keys = self.schema_loader.get_all_field_names()
        return (
            f"Fix consolidation output for {company_name}.\n"
            "Return ONLY one strict JSON object with EXACTLY these keys:\n"
            f"{json.dumps(required_keys, ensure_ascii=True)}\n\n"
            "No markdown. No code fences. No extra keys. No explanations.\n"
            f"Previous error: {error_text}\n\n"
            f"Current partial JSON:\n{json.dumps(current, ensure_ascii=True)}\n\n"
            f"Provider outputs:\n{json.dumps(responses, ensure_ascii=True)}\n"
        )
