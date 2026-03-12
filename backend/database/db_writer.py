"""Supabase writer for innovex_lc table."""
import json
import logging
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class DatabaseWriter:
    """Handles writing validated company data to innovex_lc table via Supabase."""

    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        self.client = None

        # Tunables for transient network failures (WinError 10054, timeouts, resets).
        self.max_retries = int(os.getenv("SUPABASE_MAX_RETRIES", "4"))
        self.base_backoff_seconds = float(os.getenv("SUPABASE_BACKOFF_SECONDS", "1.5"))
        self.pending_queue_path = Path("output") / "pending_supabase_uploads.jsonl"

        if not self.supabase_url or not self.supabase_key:
            logger.warning("Supabase credentials missing: SUPABASE_URL / SUPABASE_ANON_KEY")
            return

        try:
            from supabase import ClientOptions, create_client

            options = ClientOptions(postgrest_client_timeout=30)
            self.client = create_client(self.supabase_url, self.supabase_key, options=options)
            logger.info("Supabase client initialized")
        except Exception as e:
            logger.error("Failed to initialize Supabase client: %s", e)
            self.client = None

    def _is_transient_error(self, err: Exception) -> bool:
        text = str(err).lower()
        transient_markers = (
            "connection reset",
            "connection aborted",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "server disconnected",
            "remote host",
            "forcibly closed",
            "network",
        )
        return isinstance(err, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError, socket.timeout)) or any(
            marker in text for marker in transient_markers
        )

    def _execute_with_retry(self, operation_name: str, fn):
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                return fn()
            except Exception as e:
                last_error = e
                is_last = attempt >= self.max_retries
                if not self._is_transient_error(e) or is_last:
                    logger.error("%s failed (attempt %s/%s): %s", operation_name, attempt, self.max_retries, e)
                    break

                delay = self.base_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "%s transient error (attempt %s/%s): %s. Retrying in %.1fs",
                    operation_name,
                    attempt,
                    self.max_retries,
                    e,
                    delay,
                )
                time.sleep(delay)

        if last_error:
            raise last_error
        raise RuntimeError(f"{operation_name} failed with unknown error")

    def _queue_failed_insert(self, company_name: str, company_json: Dict[str, Any], error: Exception) -> str:
        self.pending_queue_path.parent.mkdir(parents=True, exist_ok=True)
        queued_id = f"queued:{int(time.time())}"
        queued_payload = {
            "queued_id": queued_id,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "company_name": company_name,
            "company_json": company_json,
            "error": str(error),
        }
        with self.pending_queue_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(queued_payload, ensure_ascii=False) + "\n")

        logger.warning(
            "Supabase insert queued locally (%s). File: %s",
            queued_id,
            self.pending_queue_path,
        )
        return queued_id

    def flush_pending_uploads(self) -> int:
        if not self.client or not self.pending_queue_path.exists():
            return 0

        lines = self.pending_queue_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return 0

        remaining = []
        flushed = 0

        for line in lines:
            try:
                row = json.loads(line)
                payload = {"company_name": row["company_name"], "company_json": row["company_json"]}
                self._execute_with_retry(
                    "Supabase flush insert",
                    lambda payload=payload: self.client.table("innovex_lc").insert(payload).execute(),
                )
                flushed += 1
            except Exception:
                remaining.append(line)

        if remaining:
            self.pending_queue_path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
        else:
            self.pending_queue_path.unlink(missing_ok=True)

        if flushed:
            logger.info("Flushed %s pending Supabase uploads", flushed)
        return flushed

    def save_company_data(self, company_name: str, company_json: Dict[str, Any]) -> Optional[str]:
        if not self.client:
            logger.error("Supabase client not initialized")
            return self._queue_failed_insert(company_name, company_json, RuntimeError("Supabase client not initialized"))

        # Best effort: upload pending backlog first.
        self.flush_pending_uploads()

        payload = {"company_name": company_name, "company_json": company_json}

        try:
            result = self._execute_with_retry(
                "Supabase insert",
                lambda: self.client.table("innovex_lc").insert(payload).execute(),
            )
            if result.data and len(result.data) > 0:
                record_id = result.data[0].get("id")
                logger.info("Inserted company %s with id=%s", company_name, record_id)
                return str(record_id) if record_id is not None else None

            logger.error("Insert returned no rows for company=%s", company_name)
            return self._queue_failed_insert(company_name, company_json, RuntimeError("Insert returned no rows"))
        except Exception as e:
            logger.error("Database insertion error: %s", e)
            return self._queue_failed_insert(company_name, company_json, e)

    def check_connection(self) -> bool:
        if not self.client:
            return False
        try:
            self._execute_with_retry(
                "Supabase connection check",
                lambda: self.client.table("innovex_lc").select("id").limit(1).execute(),
            )
            return True
        except Exception as e:
            logger.error("Database connection failed: %s", e)
            return False

    def get_company_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            logger.error("Supabase client not initialized")
            return None

        try:
            result = self._execute_with_retry(
                "Supabase get by id",
                lambda: self.client.table("innovex_lc").select("*").eq("id", record_id).limit(1).execute(),
            )
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error("Error retrieving company by ID: %s", e)
            return None

    def update_company_data(self, record_id: str, company_name: str, company_json: Dict[str, Any]) -> bool:
        if not self.client:
            logger.error("Supabase client not initialized")
            return False

        try:
            result = self._execute_with_retry(
                "Supabase update",
                lambda: (
                    self.client.table("innovex_lc")
                    .update(
                        {
                            "company_name": company_name,
                            "company_json": company_json,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    .eq("id", record_id)
                    .execute()
                ),
            )
            return bool(result.data)
        except Exception as e:
            logger.error("Error updating company data: %s", e)
            return False
