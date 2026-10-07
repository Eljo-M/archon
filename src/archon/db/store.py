"""Durable single-process development store. Cluster persistence is a separate milestone."""

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from archon.domain import TERMINAL, Event, Issue, RunStatus


class RunStore:
    def __init__(self, path: str = ":memory:"):
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.lock = asyncio.Lock()
        self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                fingerprint TEXT NOT NULL, issue TEXT NOT NULL,
                status TEXT NOT NULL, cancel_requested INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL REFERENCES runs(run_id), sequence INTEGER NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(run_id, sequence)
            );
        """)

    async def create(self, issue: Issue, idempotency_key: str) -> tuple[str, bool]:
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValueError("idempotency key must be between 1 and 200 characters")
        async with self.lock:
            row = self.connection.execute("SELECT * FROM runs WHERE idempotency_key=?",
                                          (idempotency_key,)).fetchone()
            if row:
                if row["fingerprint"] != issue.fingerprint():
                    raise ValueError("idempotency key already belongs to a different request")
                return row["run_id"], False
            run_id = str(uuid4())
            with self.connection:
                self.connection.execute("INSERT INTO runs VALUES (?,?,?,?,?,0)",
                                        (run_id, idempotency_key, issue.fingerprint(),
                                         json.dumps(issue.to_dict()), RunStatus.QUEUED))
                self._append(Event(run_id, 0, "QUEUED", "gateway", "Issue accepted",
                                   status=RunStatus.QUEUED))
            return run_id, True

    def _append(self, event: Event) -> Event:
        row = self.connection.execute("SELECT status FROM runs WHERE run_id=?", (event.run_id,)).fetchone()
        if row is None:
            raise KeyError(event.run_id)
        if RunStatus(row["status"]) in TERMINAL:
            raise ValueError("cannot append events to a terminal run")
        event.sequence = self.connection.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?", (event.run_id,)
        ).fetchone()[0]
        event.timestamp = datetime.now(UTC).isoformat()
        self.connection.execute("INSERT INTO events VALUES (?,?,?)",
                                (event.run_id, event.sequence, json.dumps(event.to_dict())))
        self.connection.execute("UPDATE runs SET status=? WHERE run_id=?", (event.status, event.run_id))
        return event

    async def append(self, event: Event) -> Event:
        async with self.lock:
            with self.connection:
                return self._append(event)

    async def get(self, run_id: str) -> dict:
        async with self.lock:
            row = self.connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            result = dict(row)
            result["issue"] = Issue.from_dict(json.loads(row["issue"]))
            result["status"] = RunStatus(row["status"])
            return result

    async def events(self, run_id: str, after: int = 0) -> list[Event]:
        if after < 0:
            raise ValueError("event cursor cannot be negative")
        async with self.lock:
            rows = self.connection.execute("SELECT payload FROM events WHERE run_id=? AND sequence>? "
                                           "ORDER BY sequence", (run_id, after)).fetchall()
            return [Event(**json.loads(row[0])) for row in rows]

    async def poll(self, run_id: str, after: int = 0) -> tuple[list[Event], RunStatus]:
        """Read events and lifecycle state from one snapshot to avoid missing the terminal event."""
        if after < 0:
            raise ValueError("event cursor cannot be negative")
        async with self.lock:
            run = self.connection.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise KeyError(run_id)
            rows = self.connection.execute("SELECT payload FROM events WHERE run_id=? AND sequence>? "
                                           "ORDER BY sequence", (run_id, after)).fetchall()
            return [Event(**json.loads(row[0])) for row in rows], RunStatus(run[0])

    async def cancel(self, run_id: str) -> bool:
        async with self.lock:
            row = self.connection.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            if RunStatus(row[0]) in TERMINAL:
                return False
            with self.connection:
                self.connection.execute("UPDATE runs SET cancel_requested=1 WHERE run_id=?", (run_id,))
            return True

    async def recover_interrupted(self) -> int:
        """Fail incomplete development jobs explicitly; do not silently resume incomplete attempts."""
        async with self.lock:
            rows = self.connection.execute("SELECT run_id FROM runs WHERE status IN ('QUEUED','RUNNING')").fetchall()
            with self.connection:
                for row in rows:
                    self._append(Event(row[0], 0, "FAILED", "gateway", "Server interrupted before completion",
                                       status=RunStatus.FAILED, evidence={"category": "INFRA_ERROR"}))
            return len(rows)

    def close(self):
        self.connection.close()
