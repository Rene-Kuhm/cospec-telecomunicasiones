import uuid
from datetime import UTC, datetime

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class CospecException(Exception):
    def __init__(
        self,
        error_type: str,
        code: str,
        message: str,
        http_status: int,
        trace_id: str = "",
    ) -> None:
        self.error_type = error_type
        self.code = code
        self.message = message
        self.http_status = http_status
        self.trace_id = trace_id or str(uuid.uuid4())
        super().__init__(message)


class AuthError(CospecException):
    def __init__(self, code: str = "UNAUTHORIZED", message: str = "Authentication required", trace_id: str = "") -> None:
        super().__init__("AuthError", code, message, 401, trace_id)


class ForbiddenError(CospecException):
    def __init__(self, code: str = "FORBIDDEN", message: str = "Access denied", trace_id: str = "") -> None:
        super().__init__("ForbiddenError", code, message, 403, trace_id)


class NotFoundError(CospecException):
    def __init__(self, code: str = "NOT_FOUND", message: str = "Resource not found", trace_id: str = "") -> None:
        super().__init__("NotFoundError", code, message, 404, trace_id)


class ValidationError(CospecException):
    def __init__(self, code: str = "VALIDATION_ERROR", message: str = "Validation failed", trace_id: str = "") -> None:
        super().__init__("ValidationError", code, message, 422, trace_id)


class ConflictError(CospecException):
    def __init__(self, code: str = "CONFLICT", message: str = "Resource conflict", trace_id: str = "") -> None:
        super().__init__("ConflictError", code, message, 409, trace_id)


class RateLimitError(CospecException):
    def __init__(self, code: str = "RATE_LIMIT_EXCEEDED", message: str = "Rate limit exceeded", trace_id: str = "") -> None:
        super().__init__("RateLimitError", code, message, 429, trace_id)


class InternalError(CospecException):
    def __init__(self, code: str = "INTERNAL_ERROR", message: str = "An internal error occurred", trace_id: str = "") -> None:
        super().__init__("InternalError", code, message, 500, trace_id)


# Factory functions for common errors
def ticket_not_found(ticket_id: str) -> NotFoundError:
    return NotFoundError(
        code="TICKET_NOT_FOUND",
        message=f"Ticket '{ticket_id}' not found",
    )


def invalid_transition(from_status: str, to_status: str) -> ValidationError:
    return ValidationError(
        code="INVALID_TRANSITION",
        message=f"Cannot transition ticket from '{from_status}' to '{to_status}'",
    )


def checklist_incomplete() -> ValidationError:
    return ValidationError(
        code="CHECKLIST_INCOMPLETE",
        message="All checklist items must be completed before closing the ticket",
    )


def no_evidence() -> ValidationError:
    return ValidationError(
        code="NO_EVIDENCE",
        message="At least one evidence attachment is required before closing the ticket",
    )


def assignment_no_candidate() -> ValidationError:
    return ValidationError(
        code="NO_CANDIDATE_FOUND",
        message="No suitable technician found for auto-assignment",
    )


def _build_error_body(exc: CospecException) -> dict:
    return {
        "success": False,
        "data": None,
        "error": {
            "type": exc.error_type,
            "code": exc.code,
            "message": exc.message,
            "trace_id": exc.trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        "meta": {
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "v1",
        },
    }


async def cospec_exception_handler(request: Request, exc: CospecException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=_build_error_body(exc),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    trace_id = str(uuid.uuid4())
    errors = exc.errors()
    message = "; ".join(
        f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in errors
    )
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "error": {
                "type": "ValidationError",
                "code": "REQUEST_VALIDATION_ERROR",
                "message": message,
                "trace_id": trace_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            "meta": {
                "timestamp": datetime.now(UTC).isoformat(),
                "version": "v1",
            },
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = str(uuid.uuid4())
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": {
                "type": "InternalError",
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "trace_id": trace_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            "meta": {
                "timestamp": datetime.now(UTC).isoformat(),
                "version": "v1",
            },
        },
    )
