import pytest

from app.core.enums import TICKET_TRANSITIONS, TicketStatus
from app.core.exceptions import ValidationError
from app.services.ticket import TicketService


def test_valid_transitions():
    """All defined transitions should be valid."""
    valid_pairs = [
        (TicketStatus.ABIERTO, TicketStatus.ASIGNADO),
        (TicketStatus.ASIGNADO, TicketStatus.EN_RUTA),
        (TicketStatus.ASIGNADO, TicketStatus.ABIERTO),
        (TicketStatus.EN_RUTA, TicketStatus.EN_SITIO),
        (TicketStatus.EN_RUTA, TicketStatus.ASIGNADO),
        (TicketStatus.EN_SITIO, TicketStatus.EN_TRABAJO),
        (TicketStatus.EN_SITIO, TicketStatus.ASIGNADO),
        (TicketStatus.EN_TRABAJO, TicketStatus.RESUELTO),
        (TicketStatus.EN_TRABAJO, TicketStatus.ASIGNADO),
        (TicketStatus.RESUELTO, TicketStatus.CERRADO),
        (TicketStatus.RESUELTO, TicketStatus.ASIGNADO),
    ]
    for from_status, to_status in valid_pairs:
        allowed = TICKET_TRANSITIONS[from_status]
        assert to_status in allowed, (
            f"Expected {to_status} to be a valid transition from {from_status}"
        )


def test_invalid_transition_raises_error():
    """Invalid transitions should raise ValidationError."""
    from app.core.exceptions import invalid_transition  # noqa: PLC0415

    invalid_pairs = [
        (TicketStatus.ABIERTO, TicketStatus.CERRADO),
        (TicketStatus.ABIERTO, TicketStatus.EN_RUTA),
        (TicketStatus.CERRADO, TicketStatus.ABIERTO),
        (TicketStatus.CERRADO, TicketStatus.RESUELTO),
        (TicketStatus.EN_TRABAJO, TicketStatus.CERRADO),
    ]
    for from_status, to_status in invalid_pairs:
        allowed = TICKET_TRANSITIONS[from_status]
        assert to_status not in allowed, (
            f"Expected {to_status} to NOT be valid from {from_status}"
        )

        exc = invalid_transition(str(from_status), str(to_status))
        assert isinstance(exc, ValidationError)
        assert exc.http_status == 422
        assert exc.code == "INVALID_TRANSITION"
        assert str(from_status) in exc.message
        assert str(to_status) in exc.message


def test_all_states_have_valid_next_states():
    """Every TicketStatus except CERRADO must have at least one valid next state."""
    for status in TicketStatus:
        transitions = TICKET_TRANSITIONS.get(status, [])
        if status == TicketStatus.CERRADO:
            assert len(transitions) == 0, "CERRADO should have no valid transitions"
        else:
            assert len(transitions) > 0, (
                f"Status {status} should have at least one valid transition"
            )


def test_closed_state_has_no_transitions():
    """CERRADO is a terminal state."""
    assert TICKET_TRANSITIONS[TicketStatus.CERRADO] == []


def test_transition_dict_covers_all_statuses():
    """All TicketStatus values should be keys in TICKET_TRANSITIONS."""
    for status in TicketStatus:
        assert status in TICKET_TRANSITIONS, (
            f"Missing transition entry for status: {status}"
        )
