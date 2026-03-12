"""Main orchestration entry point using LangGraph stateful workflow."""
import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from core.field_comparator import FieldComparator
from core.prompt_constructor import PromptConstructor
from core.schema_loader import SchemaLoader
from database.db_writer import DatabaseWriter
from orchestration.consolidator import Consolidator
from orchestration.generator import ParallelGenerator
from orchestration.graph import LangGraphPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("pipeline.log")],
)
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


def setup_langsmith() -> None:
    """Enable LangSmith tracing when configured via environment variables."""
    tracing_enabled = os.getenv("LANGSMITH_TRACING", "").strip().lower() == "true"
    api_key = os.getenv("LANGSMITH_API_KEY", "").strip()
    if not tracing_enabled:
        return
    if not api_key:
        logger.warning("LangSmith tracing requested but LANGSMITH_API_KEY is empty")
        return

    # Ensure compatibility env vars are set for LangChain/LangGraph tracing.
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", api_key)
    os.environ.setdefault("LANGCHAIN_ENDPOINT", os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"))
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "innovex-lc"))

    try:
        from langsmith import Client

        Client()
        logger.info("LangSmith tracing enabled (project=%s)", os.environ.get("LANGCHAIN_PROJECT"))
    except Exception as exc:
        logger.warning("LangSmith init failed: %s", exc)


class OrchestrationPipeline:
    """Facade exposing the existing public API while delegating execution to LangGraph."""

    def __init__(self, config_dir: str = "config", max_retries: int = 1):
        self.config_dir = Path(config_dir)
        self.max_retries = max_retries

        self.schema_loader = SchemaLoader(str(self.config_dir / "field_constraints.json"))
        self.prompt_constructor = PromptConstructor(self.schema_loader)
        self.field_comparator = FieldComparator()
        self.generator = ParallelGenerator(
            expected_fields=self.schema_loader.get_all_field_names(),
            max_retries=max_retries,
        )
        self.consolidator = Consolidator(max_retries=2, schema_loader=self.schema_loader)
        self.db_writer = DatabaseWriter()
        self.graph_runner = LangGraphPipeline(
            schema_loader=self.schema_loader,
            prompt_constructor=self.prompt_constructor,
            generator=self.generator,
            consolidator=self.consolidator,
            db_writer=self.db_writer,
        )

    async def generate(self, company_name: str, verbose: bool = True, progress_callback=None) -> Dict[str, Any]:
        logger.info("=" * 80)
        logger.info("Starting strict LangGraph pipeline for: %s", company_name)
        logger.info("=" * 80)

        result_state = await self.graph_runner.run(company_name, progress_callback=progress_callback)
        if result_state.get("status") == "error":
            raise ValueError(result_state.get("error", "Pipeline failed"))

        comparison = self.field_comparator.compare(result_state.get("validated_outputs", {}))
        return {
            "status": "success",
            "company_name": company_name,
            "company_json": result_state["final_output"],
            "confidence": self._calculate_confidence(comparison),
            "comparison": comparison,
            "validation_report": result_state.get("pydantic_report", {}),
            "pytest_report": result_state.get("pytest_report", {}),
            "attempt": 1,
            "database_id": result_state.get("database_id"),
            "events": result_state.get("events", []),
        }

    def _calculate_confidence(self, comparison_results: Dict[str, Any]) -> float:
        unanimous = len(comparison_results["unanimous_fields"])
        majority = len(comparison_results["majority_fields"])
        conflicts = len(comparison_results["conflicting_fields"])
        missing = len(comparison_results["missing_fields"])
        total = unanimous + majority + conflicts + missing
        if total == 0:
            return 0.0
        confidence = (unanimous * 1.0 + majority * 0.7 + conflicts * 0.3 + missing * 0.2) / total
        return min(1.0, confidence)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run strict LangGraph Innovex pipeline")
    parser.add_argument("--company", type=str, help="Company name to process")
    parser.add_argument(
        "--show-graph",
        action="store_true",
        help="Export LangGraph structure to output/langgraph_mermaid.md",
    )
    parser.add_argument(
        "--graph-only",
        action="store_true",
        help="Export LangGraph structure and exit without running providers",
    )
    args = parser.parse_args()

    setup_langsmith()

    company_name = args.company.strip() if args.company else input("Enter company name: ").strip()
    if not company_name:
        raise ValueError("Company name is required")

    pipeline = OrchestrationPipeline(config_dir="config", max_retries=1)

    if args.show_graph or args.graph_only:
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        mermaid_path = output_dir / "langgraph_mermaid.md"
        try:
            graph_view = pipeline.graph_runner.graph.get_graph()
            mermaid = graph_view.draw_mermaid()
            mermaid_path.write_text(f"```mermaid\n{mermaid}\n```\n", encoding="utf-8")
            logger.info("LangGraph mermaid exported to: %s", mermaid_path)
        except Exception as exc:
            logger.warning("Could not export graph mermaid: %s", exc)
        if args.graph_only:
            return

    result = await pipeline.generate(company_name, verbose=True)

    logger.info(
        json.dumps(
            {
                "status": result["status"],
                "company_name": result["company_name"],
                "confidence": f"{result['confidence']:.2%}",
                "attempt": result["attempt"],
                "fields_generated": len(result["company_json"]),
                "database_id": result.get("database_id", "Not saved"),
            },
            indent=2,
        )
    )

    output_file = Path("output") / f"{company_name.replace(' ', '_')}_result.json"
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info("Result saved to: %s", output_file)


if __name__ == "__main__":
    asyncio.run(main())
