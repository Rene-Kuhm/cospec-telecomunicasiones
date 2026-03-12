import asyncio
import uuid
from collections import defaultdict

import structlog

log = structlog.get_logger(__name__)


class SSEBroadcaster:
    """Manages SSE connections per user and per role."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, list[asyncio.Queue]] = defaultdict(list)
        # Maps queue -> role for role-based broadcast
        self._queue_roles: dict[int, str] = {}

    async def subscribe(self, user_id: uuid.UUID, role: str = "") -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._connections[user_id].append(queue)
        if role:
            self._queue_roles[id(queue)] = role
        log.info("sse_subscribed", user_id=str(user_id))
        return queue

    async def unsubscribe(self, user_id: uuid.UUID, queue: asyncio.Queue) -> None:
        queues = self._connections.get(user_id, [])
        if queue in queues:
            queues.remove(queue)
        self._queue_roles.pop(id(queue), None)
        if not queues:
            self._connections.pop(user_id, None)
        log.info("sse_unsubscribed", user_id=str(user_id))

    async def broadcast_to_user(
        self,
        user_id: uuid.UUID,
        event_type: str,
        data: dict,
    ) -> None:
        queues = self._connections.get(user_id, [])
        for queue in queues:
            try:
                queue.put_nowait({"type": event_type, "data": data})
            except asyncio.QueueFull:
                log.warning("sse_queue_full", user_id=str(user_id), event_type=event_type)

    async def broadcast_to_role(
        self,
        role: str,
        event_type: str,
        data: dict,
    ) -> None:
        for user_id, queues in list(self._connections.items()):
            for queue in queues:
                if self._queue_roles.get(id(queue)) == role:
                    try:
                        queue.put_nowait({"type": event_type, "data": data})
                    except asyncio.QueueFull:
                        log.warning("sse_queue_full", role=role, event_type=event_type)

    async def broadcast_all(self, event_type: str, data: dict) -> None:
        for user_id, queues in list(self._connections.items()):
            for queue in queues:
                try:
                    queue.put_nowait({"type": event_type, "data": data})
                except asyncio.QueueFull:
                    log.warning("sse_queue_full", event_type=event_type)


broadcaster = SSEBroadcaster()
