import asyncio
import json
import uuid

import structlog
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.core.exceptions import AuthError
from app.core.security import decode_access_token
from app.database import get_db
from app.repositories.user import UserRepository
from app.services.sse import broadcaster

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/events", tags=["sse"])


@router.get("")
async def sse_stream(
    token: str | None = Query(None),
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    # Accept token from query param (for SSE clients that can't set headers) or Authorization header
    raw_token: str | None = None
    if token:
        raw_token = token
    elif authorization and authorization.startswith("Bearer "):
        raw_token = authorization.removeprefix("Bearer ")

    if not raw_token:
        raise AuthError(code="MISSING_TOKEN", message="Authentication required for SSE")

    payload = decode_access_token(raw_token)
    user_id_str = payload.get("sub")
    role = payload.get("role", "")
    if not user_id_str:
        raise AuthError(code="INVALID_TOKEN", message="Token missing subject")

    user_uuid = uuid.UUID(user_id_str)
    repo = UserRepository(db)
    user = await repo.get_by_id(user_uuid)
    if user is None or not user.active:
        raise AuthError(code="USER_NOT_FOUND", message="User not found")

    async def event_generator():
        queue = await broadcaster.subscribe(user_uuid, role=role)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=float(settings.SSE_KEEPALIVE_SECONDS),
                    )
                    yield {
                        "event": event["type"],
                        "data": json.dumps(event["data"]),
                        "id": str(uuid.uuid4()),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            await broadcaster.unsubscribe(user_uuid, queue)
            log.info("sse_disconnected", user_id=user_id_str)

    return EventSourceResponse(event_generator())
