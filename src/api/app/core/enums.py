from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    TECH = "tech"
    CUSTOMER = "customer"


class TicketStatus(StrEnum):
    ABIERTO = "abierto"
    ASIGNADO = "asignado"
    EN_RUTA = "en_ruta"
    EN_SITIO = "en_sitio"
    EN_TRABAJO = "en_trabajo"
    RESUELTO = "resuelto"
    CERRADO = "cerrado"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GeocodingStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class AppointmentStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"


class AttachmentType(StrEnum):
    PHOTO = "photo"
    DOC = "doc"
    NOTE = "note"


class ExportKind(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"
    ANNUAL = "annual"


class ExportStatus(StrEnum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ChecklistItemStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"


class TicketEventType(StrEnum):
    CREATED = "created"
    ASSIGNED = "assigned"
    STATUS_CHANGED = "status_changed"
    EVIDENCE_ADDED = "evidence_added"
    EVIDENCE_EDITED = "evidence_edited"
    EVIDENCE_DELETED = "evidence_deleted"
    MESSAGE_SENT = "message_sent"
    RESCHEDULED = "rescheduled"
    CLOSED = "closed"
    SLA_BREACH = "sla_breach"
    AI_QUERIED = "ai_queried"
    GEOCODED = "geocoded"


# Valid state transitions
TICKET_TRANSITIONS: dict[TicketStatus, list[TicketStatus]] = {
    TicketStatus.ABIERTO: [TicketStatus.ASIGNADO],
    TicketStatus.ASIGNADO: [TicketStatus.EN_RUTA, TicketStatus.ABIERTO],
    TicketStatus.EN_RUTA: [TicketStatus.EN_SITIO, TicketStatus.ASIGNADO],
    TicketStatus.EN_SITIO: [TicketStatus.EN_TRABAJO, TicketStatus.ASIGNADO],
    TicketStatus.EN_TRABAJO: [TicketStatus.RESUELTO, TicketStatus.ASIGNADO],
    TicketStatus.RESUELTO: [TicketStatus.CERRADO, TicketStatus.ASIGNADO],
    TicketStatus.CERRADO: [],
}
