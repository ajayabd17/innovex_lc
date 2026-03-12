"""In-memory run store with JSONL durability."""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunRecord:
    run_id: str
    company_name: str
    status: str
    attempt: int
    parent_run_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    error: Optional[str] = None
    database_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    events: Optional[list[dict[str, Any]]] = None
    created_at: str = field(default_factory=_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: str = field(default_factory=_now_iso)


class RunStore:
    """Primary in-memory state with append-only JSONL events."""

    def __init__(self, jsonl_path: str, memory_limit: int = 2000):
        self.jsonl_path = Path(jsonl_path)
        self.memory_limit = max(100, int(memory_limit))
        self._runs: "OrderedDict[str, RunRecord]" = OrderedDict()
        self._lock = threading.Lock()
        self.load_from_jsonl()

    def _prune_if_needed(self) -> None:
        while len(self._runs) > self.memory_limit:
            self._runs.popitem(last=False)

    def append_event(self, event: Dict[str, Any]) -> None:
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def _to_event(self, record: RunRecord, event_type: str) -> Dict[str, Any]:
        return {
            "event_type": event_type,
            "timestamp": _now_iso(),
            "record": asdict(record),
        }

    def load_from_jsonl(self) -> None:
        if not self.jsonl_path.exists():
            return
        with self._lock:
            for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    record_data = event.get("record") or {}
                    run_id = record_data.get("run_id")
                    if not run_id:
                        continue
                    self._runs[run_id] = RunRecord(**record_data)
                    self._runs.move_to_end(run_id)
                except Exception:
                    continue
            self._prune_if_needed()

    def create_run(
        self,
        company_name: str,
        attempt: int = 1,
        parent_run_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RunRecord:
        with self._lock:
            record = RunRecord(
                run_id=str(uuid4()),
                company_name=company_name,
                status="queued",
                attempt=attempt,
                parent_run_id=parent_run_id,
                idempotency_key=idempotency_key,
            )
            self._runs[record.run_id] = record
            self._runs.move_to_end(record.run_id)
            self._prune_if_needed()
            self.append_event(self._to_event(record, "queued"))
            return record

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        with self._lock:
            record = self._runs.get(run_id)
            return RunRecord(**asdict(record)) if record else None

    def mark_running(self, run_id: str) -> Optional[RunRecord]:
        with self._lock:
            record = self._runs.get(run_id)
            if not record:
                return None
            record.status = "running"
            if record.events is None:
                record.events = []
            record.started_at = _now_iso()
            record.updated_at = _now_iso()
            self.append_event(self._to_event(record, "running"))
            return RunRecord(**asdict(record))

    def mark_progress(self, run_id: str, event: Dict[str, Any]) -> Optional[RunRecord]:
        with self._lock:
            record = self._runs.get(run_id)
            if not record:
                return None
            if record.events is None:
                record.events = []
            record.events.append(event)
            record.updated_at = _now_iso()
            self.append_event(self._to_event(record, "progress"))
            return RunRecord(**asdict(record))

    def mark_succeeded(
        self,
        run_id: str,
        result: Dict[str, Any],
        database_id: Optional[str],
        events: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[RunRecord]:
        with self._lock:
            record = self._runs.get(run_id)
            if not record:
                return None
            record.status = "succeeded"
            record.result = result
            record.database_id = database_id
            record.events = events
            record.completed_at = _now_iso()
            record.updated_at = _now_iso()
            self.append_event(self._to_event(record, "succeeded"))
            return RunRecord(**asdict(record))

    def mark_failed(
        self,
        run_id: str,
        error: str,
        events: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[RunRecord]:
        with self._lock:
            record = self._runs.get(run_id)
            if not record:
                return None
            record.status = "failed"
            record.error = error
            record.events = events
            record.completed_at = _now_iso()
            record.updated_at = _now_iso()
            self.append_event(self._to_event(record, "failed"))
            return RunRecord(**asdict(record))

    def find_by_idempotency(self, company_name: str, idempotency_key: str) -> Optional[RunRecord]:
        with self._lock:
            for record in reversed(self._runs.values()):
                if record.company_name != company_name:
                    continue
                if record.idempotency_key != idempotency_key:
                    continue
                if record.status in {"queued", "running", "succeeded"}:
                    return RunRecord(**asdict(record))
            return None

    def status_counts(self) -> Dict[str, int]:
        with self._lock:
            counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
            for record in self._runs.values():
                if record.status in counts:
                    counts[record.status] += 1
            return counts
