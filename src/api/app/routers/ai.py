import uuid

import httpx
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.enums import TicketEventType
from app.core.exceptions import InternalError, NotFoundError, ticket_not_found
from app.database import get_db
from app.dependencies import get_admin_or_tech
from app.models.user import User
from app.repositories.ticket import TicketRepository
from app.schemas.common import ApiResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["ai"])


class AIQueryRequest(BaseModel):
    question: str


class AIQueryResponse(BaseModel):
    answer: str
    model: str


@router.post("/{ticket_id}/ai-query", response_model=ApiResponse[AIQueryResponse])
async def ai_query(
    ticket_id: uuid.UUID,
    body: AIQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_or_tech),
) -> ApiResponse[AIQueryResponse]:
    if not settings.AI_ENABLED or not settings.MINIMAX_API_KEY:
        raise InternalError(
            code="AI_DISABLED",
            message="AI assistant is not enabled or configured",
        )

    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    # Build context from ticket
    context = (
        f"Ticket ID: {ticket.id}\n"
        f"Title: {ticket.title}\n"
        f"Description: {ticket.description}\n"
        f"Category: {ticket.category}\n"
        f"Priority: {ticket.priority}\n"
        f"Status: {ticket.status}\n"
        f"Address: {ticket.address or 'N/A'}\n"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful technical support assistant for Cospec Telecomunicaciones. "
                "You help technicians diagnose and resolve telecommunications issues. "
                "Answer concisely and in Spanish."
            ),
        },
        {
            "role": "user",
            "content": f"Contexto del ticket:\n{context}\n\nPregunta: {body.question}",
        },
    ]

    try:
        async with httpx.AsyncClient(timeout=settings.MINIMAX_TIMEOUT_SECONDS) as client:
            response = await client.post(
                settings.MINIMAX_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.MINIMAX_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.MINIMAX_MODEL,
                    "messages": messages,
                    "max_tokens": 500,
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            result = response.json()
            answer = result["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        raise InternalError(
            code="AI_TIMEOUT",
            message="AI service timed out. Please try again.",
        )
    except Exception as exc:
        log.error("ai_query_failed", ticket_id=str(ticket_id), error=str(exc))
        raise InternalError(
            code="AI_ERROR",
            message="AI service unavailable. Please try again.",
        )

    await repo.create_event(
        ticket_id=ticket_id,
        actor_id=current_user.id,
        event_type=TicketEventType.AI_QUERIED,
        payload={"question": body.question, "model": settings.MINIMAX_MODEL},
    )

    return ApiResponse.ok(
        AIQueryResponse(answer=answer, model=settings.MINIMAX_MODEL)
    )
