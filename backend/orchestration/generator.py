"""Sequential LLM generation with configurable quorum and strict schema contract checks."""
import asyncio
import ast
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Set

from llm.baseten_client import get_baseten
from llm.fireworks_client import get_fireworks
from llm.groq_client import get_groq
from validators.pydantic_model import validate_output

logger = logging.getLogger(__name__)


class ParallelGenerator:
    """Generates company data from LLM providers sequentially."""

    def __init__(self, expected_fields: List[str], max_retries: int = 2):
        self.max_retries = 1
        self.expected_fields_list: List[str] = list(expected_fields)
        self.expected_fields: Set[str] = set(expected_fields)
        # 30-field mode should default to one chunk; larger schemas can override via .env.
        self.chunk_size = int(os.getenv("GENERATION_CHUNK_SIZE", "30"))
        configured = os.getenv("GENERATION_PROVIDERS", "fireworks,groq,baseten")
        self.providers = [p.strip() for p in configured.split(",") if p.strip()]
        valid = {"groq", "fireworks", "baseten"}
        unknown = [p for p in self.providers if p not in valid]
        if unknown:
            raise ValueError(f"Unknown providers in GENERATION_PROVIDERS: {unknown}")
        if len(self.providers) < 1:
            raise ValueError("GENERATION_PROVIDERS must include at least 1 provider")
        self.min_success_models = int(os.getenv("MIN_SUCCESS_MODELS", "2"))
        if self.min_success_models < 1:
            raise ValueError("MIN_SUCCESS_MODELS must be >= 1")
        if self.min_success_models > len(self.providers):
            raise ValueError(
                f"MIN_SUCCESS_MODELS={self.min_success_models} cannot exceed configured providers={len(self.providers)}"
            )
        self.generation_log = []
        self.max_rate_limit_retries = int(os.getenv("PROVIDER_RATE_LIMIT_RETRIES", "3"))
        self.rate_limit_base_delay = float(os.getenv("PROVIDER_RATE_LIMIT_BASE_DELAY_SEC", "1.5"))
        self.provider_cooldown_sec = int(os.getenv("PROVIDER_COOLDOWN_SEC", "90"))
        self._provider_cooldown_until: Dict[str, float] = {}

    async def generate_all(self, company_name: str, prompt_constructor) -> Dict[str, Dict[str, Any]]:
        logger.info(
            "Starting sequential generation from %d LLMs (min success required: %d)",
            len(self.providers),
            self.min_success_models,
        )

        responses: Dict[str, Dict[str, Any]] = {}
        failures: Dict[str, str] = {}
        for provider in self.providers:
            try:
                model_name, model_response = await self._run_provider(provider, company_name, prompt_constructor)
                responses[model_name] = model_response
            except Exception as e:
                failures[provider] = str(e)
                logger.warning("[%s] failed: %s", provider, e)

        if len(responses) < self.min_success_models:
            failure_text = " | ".join(f"{k}: {v}" for k, v in failures.items()) or "unknown failure"
            raise ValueError(
                f"Generation quorum failed. Needed {self.min_success_models}/{len(self.providers)} successful providers, "
                f"got {len(responses)}. Failures: {failure_text}"
            )

        if failures:
            logger.warning(
                "Proceeding with %d successful provider(s); failed providers: %s",
                len(responses),
                ", ".join(sorted(failures.keys())),
            )

        return responses

    async def _run_provider(self, provider: str, company_name: str, prompt_constructor) -> tuple[str, Dict[str, Any]]:
        cooldown_until = self._provider_cooldown_until.get(provider, 0.0)
        if cooldown_until > time.time():
            remaining = int(cooldown_until - time.time())
            raise ValueError(f"[{provider}] skipped due to active rate-limit cooldown ({remaining}s remaining)")
        result = await self._generate_once(provider, company_name, prompt_constructor)
        return provider, result

    async def _generate_once(self, model_name: str, company_name: str, prompt_constructor) -> Dict[str, Any]:
        logger.info("[%s] Generation attempt 1/1", model_name)
        parsed = await self._generate_in_chunks(model_name, company_name, prompt_constructor)
        parsed = await self._validate_and_repair_once(model_name, company_name, parsed, prompt_constructor)
        self.generation_log.append(
            {
                "model": model_name,
                "attempt": 1,
                "status": "success",
                "fields_count": len(parsed),
            }
        )
        return parsed

    async def _generate_in_chunks(self, model_name: str, company_name: str, prompt_constructor) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        total_fields = len(self.expected_fields_list)
        chunks = [
            self.expected_fields_list[i : i + self.chunk_size]
            for i in range(0, total_fields, self.chunk_size)
        ]

        for idx, chunk_fields in enumerate(chunks, start=1):
            logger.info("[%s] Chunk %d/%d (%d fields)", model_name, idx, len(chunks), len(chunk_fields))
            try:
                prompt = prompt_constructor.build_generation_prompt_for_fields(company_name, chunk_fields)
                response = await self._call_llm(model_name, prompt)
                parsed = self._parse_json_response(response)
                parsed = self._filter_to_expected_chunk(parsed, model_name, chunk_fields)
                self._validate_chunk_shape(parsed, model_name, chunk_fields)
                merged.update(parsed)
            except Exception as chunk_err:
                logger.warning(
                    "[%s] Chunk %d failed after partial progress (%d fields complete): %s",
                    model_name,
                    idx,
                    len(merged),
                    chunk_err,
                )
                remaining_fields = self.expected_fields_list[len(merged) :]
                recovered = await self._recover_remaining_fields(
                    model_name=model_name,
                    company_name=company_name,
                    remaining_fields=remaining_fields,
                    prompt_constructor=prompt_constructor,
                )
                merged.update(recovered)
                break

        self._validate_shape(merged, model_name)
        return merged

    async def _recover_remaining_fields(
        self,
        model_name: str,
        company_name: str,
        remaining_fields: List[str],
        prompt_constructor,
    ) -> Dict[str, Any]:
        """
        Recover only missing fields after a mid-run chunk failure.
        Strategy:
        1) Retry in smaller batches to reduce JSON truncation risk.
        2) If still failing, fallback to per-field generation.
        3) If a field still cannot be generated, set null to keep final contract complete.
        """
        if not remaining_fields:
            return {}

        logger.info("[%s] Recovery mode for %d remaining fields", model_name, len(remaining_fields))
        recovered: Dict[str, Any] = {}
        small_chunk_size = max(1, min(6, self.chunk_size // 3 if self.chunk_size > 1 else 1))

        batches = [
            remaining_fields[i : i + small_chunk_size]
            for i in range(0, len(remaining_fields), small_chunk_size)
        ]

        for batch in batches:
            if self._is_provider_in_cooldown(model_name):
                for field_name in batch:
                    recovered.setdefault(field_name, None)
                continue
            try:
                prompt = prompt_constructor.build_generation_prompt_for_fields(company_name, batch)
                response = await self._call_llm(model_name, prompt)
                parsed = self._parse_json_response(response)
                parsed = self._filter_to_expected_chunk(parsed, model_name, batch)
                self._validate_chunk_shape(parsed, model_name, batch)
                recovered.update(parsed)
            except Exception:
                # Final fallback: recover each field independently.
                for field_name in batch:
                    if self._is_provider_in_cooldown(model_name):
                        recovered[field_name] = None
                        continue
                    try:
                        prompt = prompt_constructor.build_generation_prompt_for_fields(company_name, [field_name])
                        response = await self._call_llm(model_name, prompt)
                        parsed = self._parse_json_response(response)
                        parsed = self._filter_to_expected_chunk(parsed, model_name, [field_name])
                        self._validate_chunk_shape(parsed, model_name, [field_name])
                        recovered.update(parsed)
                    except Exception as field_err:
                        logger.warning(
                            "[%s] Recovery failed for field '%s': %s. Using null.",
                            model_name,
                            field_name,
                            field_err,
                        )
                        recovered[field_name] = None

        return recovered

    async def _call_llm(self, model_name: str, prompt: str) -> str:
        loop = asyncio.get_event_loop()
        if model_name == "groq":
            llm = get_groq()
        elif model_name == "fireworks":
            llm = get_fireworks()
        elif model_name == "baseten":
            llm = get_baseten()
        else:
            raise ValueError(f"Unknown model: {model_name}")

        last_err: Exception | None = None
        for attempt in range(self.max_rate_limit_retries + 1):
            try:
                response = await loop.run_in_executor(None, lambda: llm.invoke(prompt))
                return response.content if hasattr(response, "content") else str(response)
            except Exception as e:
                last_err = e
                if not self._is_rate_limit_error(e):
                    raise
                if attempt >= self.max_rate_limit_retries:
                    self._provider_cooldown_until[model_name] = time.time() + self.provider_cooldown_sec
                    raise ValueError(
                        f"[{model_name}] rate-limited repeatedly; entering cooldown for {self.provider_cooldown_sec}s: {e}"
                    ) from e
                delay = self.rate_limit_base_delay * (2 ** attempt)
                logger.warning(
                    "[%s] 429 rate-limit detected (attempt %d/%d). Backing off %.1fs",
                    model_name,
                    attempt + 1,
                    self.max_rate_limit_retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)
        raise ValueError(str(last_err) if last_err else "Unknown LLM call failure")

    def _is_rate_limit_error(self, err: Exception) -> bool:
        text = str(err).lower()
        return (
            "429" in text
            or "rate_limit_exceeded" in text
            or "rate limited" in text
            or "too many requests" in text
        )

    def _is_provider_in_cooldown(self, provider: str) -> bool:
        return self._provider_cooldown_until.get(provider, 0.0) > time.time()

    async def _validate_and_repair_once(
        self,
        model_name: str,
        company_name: str,
        payload: Dict[str, Any],
        prompt_constructor,
    ) -> Dict[str, Any]:
        """Validate one provider output and do one targeted repair call if needed."""
        try:
            validate_output(payload)
            return payload
        except Exception as e:
            failed_fields = self._extract_failed_fields(str(e))
            if not failed_fields:
                raise ValueError(f"[{model_name}] validation failed (unable to identify fields): {e}") from e

            logger.info("[%s] Repairing %d invalid fields via targeted prompt", model_name, len(failed_fields))
            repair_prompt = prompt_constructor.build_repair_prompt_for_fields(company_name, failed_fields, payload)
            repair_response = await self._call_llm(model_name, repair_prompt)
            repaired_fields = self._parse_json_response(repair_response)
            repaired_fields = self._filter_to_expected_chunk(repaired_fields, model_name, failed_fields)
            self._validate_chunk_shape(repaired_fields, model_name, failed_fields)
            merged = dict(payload)
            merged.update(repaired_fields)
            validate_output(merged)
            return merged

    def _extract_failed_fields(self, err_text: str) -> List[str]:
        """Extract field names from Pydantic error text."""
        fields = set(re.findall(r"\n([a-z_][a-z0-9_]*)\n\s+Input should", err_text))
        if not fields:
            fields = set(re.findall(r"\n([a-z_][a-z0-9_]*)\n", err_text))
        return sorted(f for f in fields if f in self.expected_fields)

    def _parse_json_response(self, response: Any) -> Dict[str, Any]:
        response_text = self._normalize_response_text(response)
        response = response_text.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]

        cleaned = response.strip()
        try:
            data = json.loads(cleaned)
            if not isinstance(data, dict):
                raise ValueError("Response is not a JSON object")
            return data
        except json.JSONDecodeError as e:
            extracted = self._extract_json_object(cleaned)
            if extracted is not None:
                parsed = self._parse_json_with_fallbacks(extracted)
                if isinstance(parsed, dict):
                    return parsed
            parsed = self._parse_json_with_fallbacks(cleaned)
            if isinstance(parsed, dict):
                return parsed
            snippet = cleaned[:240].replace("\n", " ")
            raise ValueError(f"Invalid JSON in response: {e}. Raw snippet: {snippet}") from e

    def _parse_json_with_fallbacks(self, text: str) -> Dict[str, Any] | None:
        """Best-effort parser for non-strict model JSON (single quotes, python dict literals)."""
        candidate = text.strip()
        if not candidate:
            return None

        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        try:
            literal = ast.literal_eval(candidate)
            if isinstance(literal, dict):
                return literal
        except Exception:
            pass

        # Common LLM glitch: single-quoted JSON-ish object.
        single_quote_fixed = candidate.replace("'", '"')
        try:
            parsed = json.loads(single_quote_fixed)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        repaired = self._repair_json_like_text(candidate)
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                return parsed[0]
        except Exception:
            pass

        return None

    def _repair_json_like_text(self, text: str) -> str:
        """Repair common malformed JSON patterns from LLMs."""
        repaired = text.strip()
        repaired = repaired.replace("“", '"').replace("”", '"').replace("’", "'")
        # Quote unquoted keys: { key: ... } or , key: ...
        repaired = re.sub(r'([{\s,])([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', repaired)
        # Remove trailing commas before object/array close.
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        return repaired

    def _normalize_response_text(self, response: Any) -> str:
        """Normalize varied provider response payloads to plain text."""
        if isinstance(response, str):
            return response
        if isinstance(response, list):
            parts = []
            for item in response:
                if isinstance(item, dict):
                    txt = item.get("text")
                    if isinstance(txt, str):
                        parts.append(txt)
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        return str(response)

    def _extract_json_object(self, text: str) -> str | None:
        """Best-effort extraction of first complete JSON object from text."""
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

    def _validate_shape(self, payload: Dict[str, Any], model_name: str) -> None:
        keys = set(payload.keys())
        missing = sorted(self.expected_fields - keys)
        extra = sorted(keys - self.expected_fields)
        if missing or extra:
            parts = []
            if missing:
                parts.append(f"missing={missing[:8]} (count={len(missing)})")
            if extra:
                parts.append(f"extra={extra[:8]} (count={len(extra)})")
            raise ValueError(
                f"[{model_name}] {len(self.expected_fields_list)}-field contract violation: " + "; ".join(parts)
            )

    def _validate_chunk_shape(self, payload: Dict[str, Any], model_name: str, expected_chunk_fields: List[str]) -> None:
        expected = set(expected_chunk_fields)
        keys = set(payload.keys())
        missing = sorted(expected - keys)
        if missing:
            parts = []
            if missing:
                parts.append(f"missing={missing[:8]} (count={len(missing)})")
            raise ValueError(f"[{model_name}] chunk contract violation: " + "; ".join(parts))

    def _filter_to_expected_chunk(
        self, payload: Dict[str, Any], model_name: str, expected_chunk_fields: List[str]
    ) -> Dict[str, Any]:
        """Drop non-contract keys produced by a model while preserving required chunk keys."""
        expected = set(expected_chunk_fields)
        extras = [k for k in payload.keys() if k not in expected]
        if extras:
            logger.info(
                "[%s] Dropping %d extra keys outside chunk contract: %s",
                model_name,
                len(extras),
                extras[:8],
            )
        return {k: v for k, v in payload.items() if k in expected}
