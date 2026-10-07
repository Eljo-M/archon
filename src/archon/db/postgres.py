"""Migration entry point. Authoritative distributed run-store integration is backlog D-01."""

from importlib.resources import files

import asyncpg


async def migrate(dsn: str):
    connection = await asyncpg.connect(dsn)
    try:
        # Serialize concurrent startup migrations on one database.
        await connection.execute("SELECT pg_advisory_lock(741221)")
        for migration in sorted(files("archon.db").joinpath("migrations").iterdir(), key=lambda item: item.name):
            await connection.execute(migration.read_text(encoding="utf-8"))
    finally:
        await connection.close()
