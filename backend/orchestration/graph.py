"""LangGraph orchestration for the Innovex pipeline."""
from __future__ import annotations

import asyncio
import inspect
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from core.prompt_constructor import PromptConstructor
from core.schema_loader import SchemaLoader
from database.db_writer import DatabaseWriter
from orchestration.consolidator import Consolidator
from orchestration.generator import ParallelGenerator
from orchestration.state import PipelineState
from validators.pydantic_model import CompanyData, ValidationReport, find_null_like_fields, validate_output
from validators.pytest_gate import extract_failed_fields_from_pytest_output, run_pytest_verification_report


class LangGraphPipeline:
    """Stateful graph executor for generation, consolidation, validation and persist."""

    def __init__(
        self,
        schema_loader: SchemaLoader,
        prompt_constructor: PromptConstructor,
        generator: ParallelGenerator,
        consolidator: Consolidator,
        db_writer: DatabaseWriter,
    ):
        self.schema_loader = schema_loader
        self.prompt_constructor = prompt_constructor
        self.generator = generator
        self.consolidator = consolidator
        self.db_writer = db_writer
        self.critical_fields = {
            "name",
            "category",
            "headquarters_address",
            "overview_text",
            "incorporation_year",
            "office_count",
        }
        self.provider_order = [p.strip() for p in os.getenv("GENERATION_PROVIDERS", "fireworks,groq,baseten").split(",") if p.strip()]
        self.min_success_models = int(os.getenv("MIN_SUCCESS_MODELS", "2"))
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(PipelineState)

        graph.add_node("init_state", self._node_init_state)
        graph.add_node("generate_fireworks", self._node_generate_provider)
        graph.add_node("generate_groq", self._node_generate_provider)
        graph.add_node("generate_baseten", self._node_generate_provider)
        graph.add_node("quorum_check", self._node_quorum_check)
        graph.add_node("consolidate", self._node_consolidate)
        graph.add_node("validate_consolidated", self._node_validate_consolidated)
        graph.add_node("pytest_gate", self._node_pytest_gate)
        graph.add_node("pytest_repair_once", self._node_pytest_repair_once)
        graph.add_node("persist", self._node_persist)
        graph.add_node("finalize", self._node_finalize)

        graph.add_edge(START, "init_state")
        graph.add_edge("init_state", "generate_fireworks")
        graph.add_edge("generate_fireworks", "generate_groq")
        graph.add_edge("generate_groq", "generate_baseten")
        graph.add_edge("generate_baseten", "quorum_check")

        graph.add_conditional_edges(
            "quorum_check",
            lambda s: "consolidate" if s.get("status") != "error" else "finalize",
            {"consolidate": "consolidate", "finalize": "finalize"},
        )
        graph.add_edge("consolidate", "validate_consolidated")
        graph.add_conditional_edges(
            "validate_consolidated",
            lambda s: "pytest_gate" if s.get("status") != "error" else "finalize",
            {"pytest_gate": "pytest_gate", "finalize": "finalize"},
        )
        graph.add_conditional_edges(
            "pytest_gate",
            lambda s: "persist" if s.get("status") == "pytest_pass" else "pytest_repair_once",
            {"persist": "persist", "pytest_repair_once": "pytest_repair_once"},
        )
        graph.add_conditional_edges(
            "pytest_repair_once",
            lambda s: "validate_consolidated" if s.get("status") != "error" else "finalize",
            {"validate_consolidated": "validate_consolidated", "finalize": "finalize"},
        )
        graph.add_edge("persist", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    async def _emit_progress(self, state: PipelineState, event: Dict[str, Any]) -> None:
        callback = state.get("progress_callback")
        if not callback:
            return
        try:
            maybe = callback(event)
            if inspect.isawaitable(maybe):
                await maybe
        except Exception:
            # Progress callbacks must never break pipeline execution
            return

    async def run(self, company_name: str, progress_callback=None) -> PipelineState:
        initial_state: PipelineState = {
            "company_name": company_name,
            "required_fields": self.schema_loader.get_all_field_names(),
            "provider_order": self.provider_order,
            "raw_outputs": {},
            "validated_outputs": {},
            "provider_errors": {},
            "repair_attempts": {},
            "consolidated_output": None,
            "pydantic_report": {},
            "pytest_report": {},
            "pytest_failed_fields": [],
            "final_output": None,
            "database_id": None,
            "status": "running",
            "events": [],
            "attempt": 1,
            "active_provider": None,
            "pytest_repaired": False,
            "progress_callback": progress_callback,
        }
        return await self.graph.ainvoke(initial_state)

    async def _node_init_state(self, state: PipelineState) -> PipelineState:
        events = list(state.get("events", []))
        event = {"stage": "init_state", "status": "success", "providers": self.provider_order}
        events.append(event)
        await self._emit_progress(state, event)
        return {"events": events}

    async def _node_generate_provider(self, state: PipelineState) -> PipelineState:
        provider = None
        generated = set(state.get("raw_outputs", {}).keys()) | set(state.get("provider_errors", {}).keys())
        for p in self.provider_order:
            if p not in generated:
                provider = p
                break
        if provider is None:
            return {"active_provider": None}

        events = list(state.get("events", []))
        raw_outputs = dict(state.get("raw_outputs", {}))
        validated_outputs = dict(state.get("validated_outputs", {}))
        provider_errors = dict(state.get("provider_errors", {}))
        repair_attempts = dict(state.get("repair_attempts", {}))

        try:
            payload = await self.generator._generate_once(provider, state["company_name"], self.prompt_constructor)
            raw_outputs[provider] = payload
            gen_event = {"stage": f"generate_{provider}", "status": "success"}
            events.append(gen_event)
            await self._emit_progress(state, gen_event)

            required_fields = self.schema_loader.get_required_fields()
            null_fields = find_null_like_fields(payload, required_fields=required_fields, critical_fields=list(self.critical_fields))
            if null_fields:
                repair_prompt = self.prompt_constructor.build_repair_prompt_for_fields(state["company_name"], null_fields, payload)
                repair_response = await self.generator._call_llm(provider, repair_prompt)
                repaired = self.generator._parse_json_response(repair_response)
                repaired = self.generator._filter_to_expected_chunk(repaired, provider, null_fields)
                payload = dict(payload)
                payload.update(repaired)
                repair_attempts[provider] = repair_attempts.get(provider, 0) + 1

            validate_output(payload)
            validated_outputs[provider] = payload
            val_event = {"stage": f"validate_{provider}", "status": "success"}
            events.append(val_event)
            await self._emit_progress(state, val_event)
        except Exception as e:
            provider_errors[provider] = str(e)
            fail_event = {"stage": f"generate_{provider}", "status": "failed", "error": str(e)}
            events.append(fail_event)
            await self._emit_progress(state, fail_event)

        return {
            "raw_outputs": raw_outputs,
            "validated_outputs": validated_outputs,
            "provider_errors": provider_errors,
            "repair_attempts": repair_attempts,
            "events": events,
        }

    async def _node_quorum_check(self, state: PipelineState) -> PipelineState:
        successes = len(state.get("validated_outputs", {}))
        events = list(state.get("events", []))
        if successes < self.min_success_models:
            error = (
                f"Generation quorum failed. Needed {self.min_success_models}/{len(self.provider_order)} successful providers, "
                f"got {successes}. Failures: {state.get('provider_errors', {})}"
            )
            event = {"stage": "quorum_check", "status": "failed", "error": error}
            events.append(event)
            await self._emit_progress(state, event)
            return {"status": "error", "error": error, "events": events}
        event = {"stage": "quorum_check", "status": "success", "successes": successes}
        events.append(event)
        await self._emit_progress(state, event)
        return {"events": events}

    async def _node_consolidate(self, state: PipelineState) -> PipelineState:
        events = list(state.get("events", []))
        consolidated = await asyncio.to_thread(
            self.consolidator.consolidate,
            state["validated_outputs"],
            state["company_name"],
        )
        event = {"stage": "consolidate", "status": "success", "fields": len(consolidated)}
        events.append(event)
        await self._emit_progress(state, event)
        return {"consolidated_output": consolidated, "events": events}

    async def _node_validate_consolidated(self, state: PipelineState) -> PipelineState:
        events = list(state.get("events", []))
        try:
            consolidated = dict(state.get("consolidated_output") or {})
            validate_output(consolidated)
            report = ValidationReport(is_valid=True, validated_fields=len(consolidated)).model_dump()
            event = {"stage": "validate_consolidated", "status": "success"}
            events.append(event)
            await self._emit_progress(state, event)
            return {"pydantic_report": report, "events": events}
        except Exception as e:
            event = {"stage": "validate_consolidated", "status": "failed", "error": str(e)}
            events.append(event)
            await self._emit_progress(state, event)
            return {"status": "error", "error": str(e), "events": events}

    async def _node_pytest_gate(self, state: PipelineState) -> PipelineState:
        events = list(state.get("events", []))
        report = await asyncio.to_thread(
            run_pytest_verification_report,
            state["company_name"],
            state["consolidated_output"] or {},
        )
        if report["passed"]:
            event = {"stage": "pytest_gate", "status": "success"}
            events.append(event)
            await self._emit_progress(state, event)
            return {"pytest_report": report, "status": "pytest_pass", "events": events}
        failed_fields = extract_failed_fields_from_pytest_output(report.get("stdout", ""), report.get("stderr", ""))
        event = {"stage": "pytest_gate", "status": "failed", "failed_fields": failed_fields}
        events.append(event)
        await self._emit_progress(state, event)
        return {
            "pytest_report": report,
            "pytest_failed_fields": failed_fields,
            "status": "pytest_fail",
            "events": events,
        }

    async def _node_pytest_repair_once(self, state: PipelineState) -> PipelineState:
        events = list(state.get("events", []))
        if state.get("pytest_repaired"):
            error = "Pytest repair already attempted once and still failing"
            event = {"stage": "pytest_repair_once", "status": "failed", "error": error}
            events.append(event)
            await self._emit_progress(state, event)
            return {"status": "error", "error": error, "events": events}

        fields = list(state.get("pytest_failed_fields", []))
        if not fields:
            error = "Pytest failed but no fields could be extracted for targeted repair"
            event = {"stage": "pytest_repair_once", "status": "failed", "error": error}
            events.append(event)
            await self._emit_progress(state, event)
            return {"status": "error", "error": error, "events": events}

        available = list(state.get("validated_outputs", {}).keys())
        if not available:
            return {"status": "error", "error": "No fallback provider available for pytest repair", "events": events}

        fallback = available[0]
        payload = dict(state.get("consolidated_output") or {})
        try:
            repair_prompt = self.prompt_constructor.build_repair_prompt_for_fields(state["company_name"], fields, payload)
            response = await self.generator._call_llm(fallback, repair_prompt)
            repaired = self.generator._parse_json_response(response)
            repaired = self.generator._filter_to_expected_chunk(repaired, fallback, fields)
            payload.update(repaired)
            event = {"stage": "pytest_repair_once", "status": "success", "provider": fallback, "fields": fields}
            events.append(event)
            await self._emit_progress(state, event)
            return {"consolidated_output": payload, "pytest_repaired": True, "events": events}
        except Exception as e:
            event = {"stage": "pytest_repair_once", "status": "failed", "error": str(e)}
            events.append(event)
            await self._emit_progress(state, event)
            return {"status": "error", "error": str(e), "events": events}

    async def _node_persist(self, state: PipelineState) -> PipelineState:
        events = list(state.get("events", []))
        validated: CompanyData = validate_output(state["consolidated_output"] or {})
        final_output = self._build_canonical_company_json(validated)
        record_id = await asyncio.to_thread(
            self.db_writer.save_company_data,
            state["company_name"],
            final_output,
        )
        event = {"stage": "persist", "status": "success", "database_id": record_id}
        events.append(event)
        await self._emit_progress(state, event)
        return {"final_output": final_output, "database_id": record_id, "status": "success", "events": events}

    async def _node_finalize(self, state: PipelineState) -> PipelineState:
        status = state.get("status")
        if status == "pytest_pass":
            return {"status": "success"}
        if status == "pytest_fail":
            return {"status": "error", "error": "Pytest failed after repair attempt"}
        if status:
            if state.get("error"):
                return {"status": status, "error": state.get("error")}
            return {"status": status}
        if state.get("error"):
            return {"status": "error", "error": state.get("error")}
        if state.get("final_output"):
            return {"status": "success"}
        return {"status": "error", "error": "Pipeline ended without terminal state"}

    def _build_canonical_company_json(self, validated_data: CompanyData) -> Dict[str, Any]:
        raw = validated_data.model_dump(exclude={"company_id"})
        ordered: Dict[str, Any] = {}
        for field_name in self.schema_loader.get_all_field_names():
            ordered[field_name] = raw.get(field_name)
        return ordered


def build_graph():
    """Build compiled graph for LangGraph CLI entrypoint."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
    schema_loader = SchemaLoader("config/field_constraints.json")
    prompt_constructor = PromptConstructor(schema_loader)
    generator = ParallelGenerator(expected_fields=schema_loader.get_all_field_names(), max_retries=1)
    consolidator = Consolidator(max_retries=2, schema_loader=schema_loader)
    db_writer = DatabaseWriter()
    pipeline = LangGraphPipeline(
        schema_loader=schema_loader,
        prompt_constructor=prompt_constructor,
        generator=generator,
        consolidator=consolidator,
        db_writer=db_writer,
    )
    return pipeline.graph


# Entry variable used by langraph/langgraph CLI config:
# "./orchestration/graph.py:graph"
graph = build_graph()
