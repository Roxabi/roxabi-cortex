"""cortex-memory CLI — serve NATS workers / local inspect."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import typer

app = typer.Typer(help="cortex-memory — long-term memory satellite (MVP)")
log = logging.getLogger("cortex_memory")


def _default_db() -> Path:
    env = os.environ.get("CORTEX_MEMORY_DB")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cortex" / "memory.db"


@app.command("serve")
def serve(
    nats_url: str = typer.Option(
        None,
        "--nats-url",
        envvar="NATS_URL",
        help="NATS server URL (default env NATS_URL or nats://127.0.0.1:4222)",
    ),
    db: Path = typer.Option(
        None,
        "--db",
        help="SQLite path (default CORTEX_MEMORY_DB or ~/.cortex/memory.db)",
    ),
) -> None:
    """Run capture / search / assemble NATS workers."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    url = nats_url or os.environ.get("NATS_URL") or "nats://127.0.0.1:4222"
    db_path = db or _default_db()
    asyncio.run(_serve(url, db_path))


async def _serve(nats_url: str, db_path: Path) -> None:
    from cortex_memory.nats_worker import AssembleWorker, CaptureWorker, SearchWorker
    from cortex_memory.store import MemoryStore

    store = MemoryStore(db_path)
    log.info("store open path=%s entries=%s", db_path, store.count())

    capture = CaptureWorker(store)
    search = SearchWorker(store)
    assemble = AssembleWorker(store)

    # NatsAdapterBase.run() connects and blocks until signal. Run three
    # workers as tasks sharing process lifetime via first that exits.
    async def _run(worker, name: str) -> None:
        log.info("starting %s subject=%s", name, worker.subject)
        await worker.run(nats_url)

    try:
        await asyncio.gather(
            _run(capture, "capture"),
            _run(search, "search"),
            _run(assemble, "assemble"),
        )
    finally:
        store.close()


@app.command("stats")
def stats(
    db: Path = typer.Option(None, "--db"),
) -> None:
    """Print entry count for the local store."""
    from cortex_memory.store import MemoryStore

    path = db or _default_db()
    store = MemoryStore(path)
    try:
        typer.echo(f"db={path} entries={store.count()}")
    finally:
        store.close()


@app.command("import-vault")
def import_vault(
    vault_db: Path = typer.Option(
        Path.home() / ".roxabi-vault" / "vault.db",
        "--vault-db",
        help="Source roxabi-vault SQLite path",
    ),
    db: Path = typer.Option(None, "--db", help="Target cortex memory DB"),
    limit: int = typer.Option(0, "--limit", help="Max rows (0 = all)"),
) -> None:
    """One-shot import from ~/.roxabi-vault/vault.db into cortex store."""
    import json
    import sqlite3

    from cortex_memory.store import MemoryStore

    if not vault_db.exists():
        typer.echo(f"vault db not found: {vault_db}", err=True)
        raise typer.Exit(1)

    target = db or _default_db()
    store = MemoryStore(target)
    src = sqlite3.connect(str(vault_db))
    src.row_factory = sqlite3.Row
    sql = "SELECT * FROM entries ORDER BY id"
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = src.execute(sql).fetchall()
    n = 0
    for row in rows:
        meta_raw = row["metadata"] if "metadata" in row.keys() else "{}"
        try:
            meta = json.loads(meta_raw) if meta_raw else {}
        except json.JSONDecodeError:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        url = str(meta.get("url") or "")
        tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
        store.capture(
            title=str(row["title"]),
            body=str(row["content"]),
            category=str(row["category"]),
            entry_type=str(row["type"]),
            namespace=str(row["namespace"] if "namespace" in row.keys() else "vault"),
            url=url,
            tags=[str(t) for t in tags],
            metadata=meta,
        )
        n += 1
    src.close()
    store.close()
    typer.echo(f"imported {n} entries → {target}")


if __name__ == "__main__":
    app()
