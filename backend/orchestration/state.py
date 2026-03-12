"""LangGraph state schema for Innovex pipeline."""
from typing import Any, Dict, List, Optional, TypedDict


class PipelineState(TypedDict, total=False):
    company_name: str
    required_fields: List[str]
    provider_order: List[str]
    raw_outputs: Dict[str, Dict[str, Any]]
    validated_outputs: Dict[str, Dict[str, Any]]
    provider_errors: Dict[str, str]
    repair_attempts: Dict[str, int]
    consolidated_output: Optional[Dict[str, Any]]
    pydantic_report: Dict[str, Any]
    pytest_report: Dict[str, Any]
    pytest_failed_fields: List[str]
    final_output: Optional[Dict[str, Any]]
    database_id: Optional[str]
    status: str
    events: List[Dict[str, Any]]
    attempt: int
    active_provider: Optional[str]
    pytest_repaired: bool
    error: str
    progress_callback: Any
