"""Redis Streams transport foundation. Worker fencing/outbox integration is backlog D-01."""

import json

from redis.asyncio import Redis
from redis.exceptions import ResponseError


class TaskQueue:
    def __init__(self, url: str, stream: str = "archon:tasks", group: str = "archon:workers"):
        self.client = Redis.from_url(url, decode_responses=True)
        self.stream, self.group = stream, group

    async def initialize(self):
        try:
            await self.client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def enqueue(self, run_id: str, payload: dict) -> str:
        return await self.client.xadd(self.stream, {"run_id": run_id, "payload": json.dumps(payload)})

    async def receive(self, consumer: str, block_ms: int = 1000) -> tuple[str, dict] | None:
        rows = await self.client.xreadgroup(self.group, consumer, {self.stream: ">"}, count=1, block=block_ms)
        if not rows:
            return None
        return rows[0][1][0]

    async def reclaim(self, consumer: str, min_idle_ms: int = 60_000, cursor: str = "0-0"):
        # Callers must retain the returned cursor to scan pending entries fairly.
        return await self.client.xautoclaim(self.stream, self.group, consumer, min_idle_ms,
                                          start_id=cursor, count=1)

    async def acknowledge(self, message_id: str):
        await self.client.xack(self.stream, self.group, message_id)

    async def close(self):
        await self.client.aclose()
