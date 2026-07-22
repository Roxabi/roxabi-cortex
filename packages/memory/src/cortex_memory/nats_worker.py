"""NATS request-reply workers for cortex-memory MVP."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cortex_memory.store import estimate_tokens
from roxabi_contracts.envelope import CONTRACT_VERSION
from roxabi_contracts.memory import (
    SUBJECTS,
    AssembleItem,
    AssembleRequest,
    AssembleResponse,
    CaptureRequest,
    CaptureResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from roxabi_nats.adapter_base import NatsAdapterBase

if TYPE_CHECKING:
    from cortex_memory.store import MemoryStore

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _env_from(payload: dict[str, Any], request_id: str) -> dict[str, Any]:
    return {
        "contract_version": str(payload.get("contract_version") or CONTRACT_VERSION),
        "trace_id": str(payload.get("trace_id") or request_id),
        "issued_at": _now(),
        "job_id": str(payload.get("job_id") or request_id),
        "parent_job_id": payload.get("parent_job_id"),
    }


class CaptureWorker(NatsAdapterBase):
    def __init__(self, store: MemoryStore, *, identity_name: str = "cortex-memory") -> None:
        super().__init__(
            subject=SUBJECTS.capture,
            queue_group=SUBJECTS.workers,
            envelope_name="CaptureRequest",
            schema_version=1,
            timeout=30.0,
            heartbeat_subject=SUBJECTS.heartbeat,
            identity_name=identity_name,
            wait_ready=False,
        )
        self._store = store

    async def handle(self, msg, payload: dict) -> None:
        t0 = time.monotonic()
        try:
            req = CaptureRequest.model_validate(payload)
        except Exception as exc:
            log.warning("capture: invalid payload: %s", exc)
            return
        try:
            entry_id = self._store.capture(
                title=req.title,
                body=req.body,
                category=req.category,
                entry_type=req.entry_type,
                namespace=req.namespace,
                url=req.url,
                tags=req.tags,
                metadata=req.metadata,
            )
            resp = CaptureResponse(
                **_env_from(payload, req.request_id),
                ok=True,
                request_id=req.request_id,
                entry_id=entry_id,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            log.exception("capture failed")
            resp = CaptureResponse(
                **_env_from(payload, req.request_id),
                ok=False,
                request_id=req.request_id,
                error=str(exc)[:500],
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        await self.reply(msg, resp.model_dump_json().encode())


class SearchWorker(NatsAdapterBase):
    def __init__(self, store: MemoryStore, *, identity_name: str = "cortex-memory") -> None:
        super().__init__(
            subject=SUBJECTS.query_search,
            queue_group=SUBJECTS.workers,
            envelope_name="SearchRequest",
            schema_version=1,
            timeout=30.0,
            identity_name=identity_name,
            wait_ready=False,
        )
        self._store = store

    async def handle(self, msg, payload: dict) -> None:
        t0 = time.monotonic()
        try:
            req = SearchRequest.model_validate(payload)
        except Exception as exc:
            log.warning("search: invalid payload: %s", exc)
            return
        try:
            entries = self._store.search(
                req.query,
                namespace=req.namespace,
                category=req.category,
                limit=req.limit,
            )
            hits = [
                SearchHit(
                    entry_id=e.id,
                    title=e.title,
                    category=e.category,
                    entry_type=e.type,
                    snippet=(e.content[:240] + "…") if len(e.content) > 240 else e.content,
                    url=str(e.metadata.get("url") or ""),
                )
                for e in entries
            ]
            resp = SearchResponse(
                **_env_from(payload, req.request_id),
                ok=True,
                request_id=req.request_id,
                hits=hits,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            log.exception("search failed")
            resp = SearchResponse(
                **_env_from(payload, req.request_id),
                ok=False,
                request_id=req.request_id,
                error=str(exc)[:500],
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        await self.reply(msg, resp.model_dump_json().encode())


class AssembleWorker(NatsAdapterBase):
    def __init__(self, store: MemoryStore, *, identity_name: str = "cortex-memory") -> None:
        super().__init__(
            subject=SUBJECTS.query_assemble,
            queue_group=SUBJECTS.workers,
            envelope_name="AssembleRequest",
            schema_version=1,
            timeout=30.0,
            identity_name=identity_name,
            wait_ready=False,
        )
        self._store = store

    async def handle(self, msg, payload: dict) -> None:
        t0 = time.monotonic()
        try:
            req = AssembleRequest.model_validate(payload)
        except Exception as exc:
            log.warning("assemble: invalid payload: %s", exc)
            return
        try:
            entries, text, tokens = self._store.assemble(
                goal=req.goal,
                budget_tokens=req.budget_tokens,
                namespace=req.namespace,
                fresh_tail_days=req.fresh_tail_days,
            )
            items = [
                AssembleItem(
                    kind="entry",
                    content=f"### {e.title}\n{e.content}",
                    tokens=estimate_tokens(f"### {e.title}\n{e.content}"),
                    entry_id=e.id,
                )
                for e in entries
            ]
            resp = AssembleResponse(
                **_env_from(payload, req.request_id),
                ok=True,
                request_id=req.request_id,
                items=items,
                tokens_used=tokens,
                text=text,
                goal=req.goal,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            log.exception("assemble failed")
            resp = AssembleResponse(
                **_env_from(payload, req.request_id),
                ok=False,
                request_id=req.request_id,
                error=str(exc)[:500],
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        await self.reply(msg, resp.model_dump_json().encode())
