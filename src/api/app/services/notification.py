import structlog

from app.config import settings
from app.models.ticket import Ticket
from app.models.user import User

log = structlog.get_logger(__name__)


class NotificationService:
    async def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
    ) -> bool:
        if settings.APP_ENV == "development":
            log.info(
                "email_skipped_dev",
                to=to_email,
                subject=subject,
            )
            return True

        if not settings.BREVO_API_KEY:
            log.warning("brevo_api_key_not_set")
            return False

        try:
            import sib_api_v3_sdk  # noqa: PLC0415
            from sib_api_v3_sdk.rest import ApiException  # noqa: PLC0415

            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key["api-key"] = settings.BREVO_API_KEY
            api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
                sib_api_v3_sdk.ApiClient(configuration)
            )
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=[{"email": to_email, "name": to_name}],
                sender={"email": settings.EMAIL_FROM_ADDRESS, "name": settings.EMAIL_FROM_NAME},
                subject=subject,
                html_content=html_content,
            )
            api_instance.send_transac_email(send_smtp_email)
            log.info("email_sent", to=to_email, subject=subject)
            return True
        except Exception as exc:
            log.error("email_send_failed", to=to_email, error=str(exc))
            return False

    async def send_sms(self, to_phone: str, message: str) -> bool:
        if not settings.SMS_ENABLED:
            return False

        if settings.APP_ENV == "development":
            log.info("sms_skipped_dev", to=to_phone, message=message)
            return True

        if not settings.BREVO_API_KEY:
            log.warning("brevo_api_key_not_set")
            return False

        try:
            import sib_api_v3_sdk  # noqa: PLC0415

            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key["api-key"] = settings.BREVO_API_KEY
            api_instance = sib_api_v3_sdk.TransactionalSMSApi(
                sib_api_v3_sdk.ApiClient(configuration)
            )
            sms = sib_api_v3_sdk.SendTransacSms(
                sender=settings.SMS_SENDER_NAME,
                recipient=to_phone,
                content=message,
            )
            api_instance.send_transac_sms(sms)
            log.info("sms_sent", to=to_phone)
            return True
        except Exception as exc:
            log.error("sms_send_failed", to=to_phone, error=str(exc))
            return False

    async def notify_ticket_assigned(self, ticket: Ticket, tech: User) -> None:
        subject = f"[Cospec] Ticket asignado: {ticket.title}"
        html = (
            f"<p>Hola {tech.name},</p>"
            f"<p>Se te ha asignado el ticket <strong>#{ticket.id}</strong>: {ticket.title}</p>"
            f"<p>Prioridad: {ticket.priority} | Categoría: {ticket.category}</p>"
        )
        await self.send_email(tech.email, tech.name, subject, html)
        if tech.phone:
            msg = f"Ticket asignado: {ticket.title[:50]} | Prioridad: {ticket.priority}"
            await self.send_sms(tech.phone, msg)

    async def notify_ticket_status_changed(
        self,
        ticket: Ticket,
        new_status: str,
        recipient: User,
    ) -> None:
        subject = f"[Cospec] Ticket actualizado: {ticket.title}"
        html = (
            f"<p>Hola {recipient.name},</p>"
            f"<p>El estado del ticket <strong>{ticket.title}</strong> ha cambiado a: <strong>{new_status}</strong></p>"
        )
        await self.send_email(recipient.email, recipient.name, subject, html)

    async def notify_ticket_rescheduled(self, ticket: Ticket, recipient: User) -> None:
        subject = f"[Cospec] Cita reprogramada: {ticket.title}"
        html = (
            f"<p>Hola {recipient.name},</p>"
            f"<p>La cita para el ticket <strong>{ticket.title}</strong> ha sido reprogramada.</p>"
        )
        await self.send_email(recipient.email, recipient.name, subject, html)

    async def notify_ticket_created(self, ticket: Ticket, customer: User) -> None:
        subject = f"[Cospec] Ticket creado: {ticket.title}"
        html = (
            f"<p>Hola {customer.name},</p>"
            f"<p>Tu ticket <strong>#{ticket.id}</strong> ha sido creado exitosamente.</p>"
            f"<p>Título: {ticket.title}<br>Categoría: {ticket.category}<br>Prioridad: {ticket.priority}</p>"
        )
        await self.send_email(customer.email, customer.name, subject, html)


notification_service = NotificationService()
