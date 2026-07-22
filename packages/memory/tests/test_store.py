"""Unit tests for MemoryStore (no NATS)."""

from __future__ import annotations

from cortex_memory.store import MemoryStore


def test_capture_and_search(tmp_path) -> None:
    store = MemoryStore(tmp_path / "m.db")
    try:
        eid = store.capture(
            title="FastMCP",
            body="Build MCP servers in Python",
            category="references",
            entry_type="bookmark",
            namespace="vault",
            url="https://example.com/fastmcp",
            tags=["mcp"],
        )
        assert eid >= 1
        hits = store.search("MCP")
        assert len(hits) == 1
        assert hits[0].title == "FastMCP"
        assert hits[0].metadata.get("url") == "https://example.com/fastmcp"
    finally:
        store.close()


def test_assemble_budget(tmp_path) -> None:
    store = MemoryStore(tmp_path / "m.db")
    try:
        for i in range(5):
            store.capture(
                title=f"Note {i}",
                body="word " * 50,
                category="notes",
                entry_type="note",
                namespace="vault",
            )
        entries, text, tokens = store.assemble(
            goal=None,
            budget_tokens=40,
            namespace="vault",
            fresh_tail_days=30,
        )
        assert entries
        assert tokens <= 40 or len(entries) == 1
        assert text
    finally:
        store.close()
