import uuid

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TicketEventType
from app.core.exceptions import ticket_not_found
from app.database import get_db
from app.dependencies import get_any_role
from app.models.message import Message
from app.models.user import User
from app.repositories.ticket import TicketRepository
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.message import MessageCreateRequest, MessageOut

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["messages"])


@router.get("/{ticket_id}/messages", response_model=ApiResponse[PaginatedResponse[MessageOut]])
async def list_messages(
    ticket_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_any_role),
) -> ApiResponse[PaginatedResponse[MessageOut]]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    count_result = await db.execute(
        select(func.count()).select_from(Message).where(Message.ticket_id == ticket_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Message)
        .where(Message.ticket_id == ticket_id)
        .order_by(Message.created_at.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(result.scalars().all())
    out = [MessageOut.model_validate(m) for m in items]
    return ApiResponse.ok(PaginatedResponse.of(items=out, total=total, page=page, limit=limit))


@router.post("/{ticket_id}/messages", response_model=ApiResponse[MessageOut])
async def create_message(
    ticket_id: uuid.UUID,
    body: MessageCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_any_role),
) -> ApiResponse[MessageOut]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    message = Message(
        ticket_id=ticket_id,
        sender_id=current_user.id,
        body=body.body,
        attachment_id=body.attachment_id,
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)

    await repo.create_event(
        ticket_id=ticket_id,
        actor_id=current_user.id,
        event_type=TicketEventType.MESSAGE_SENT,
        payload={"message_id": str(message.id), "body_preview": body.body[:100]},
    )

    # Broadcast SSE
    try:
        from app.services.sse import broadcaster  # noqa: PLC0415

        await broadcaster.broadcast_to_user(
            user_id=ticket.customer_id,
            event_type="ticket.message",
            data={"ticket_id": str(ticket_id), "sender_id": str(current_user.id)},
        )
    except Exception:
        pass

    return ApiResponse.ok(MessageOut.model_validate(message))
