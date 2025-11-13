"""
Custom email backend for Resend email service.
Uses HTTP API instead of SMTP to work on Railway.
"""
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings
import resend


class ResendEmailBackend(BaseEmailBackend):
    """
    Email backend that uses Resend HTTP API for sending emails.
    Works on Railway where SMTP ports are blocked.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = settings.RESEND_API_KEY
        if self.api_key:
            resend.api_key = self.api_key

    def send_messages(self, email_messages):
        """
        Send one or more EmailMessage objects and return the number of email
        messages sent.
        """
        if not self.api_key:
            if not self.fail_silently:
                raise ValueError("RESEND_API_KEY is not set")
            return 0

        msg_count = 0
        for message in email_messages:
            try:
                # Prepare email data
                email_data = {
                    "from": message.from_email,
                    "to": message.to,
                    "subject": message.subject,
                }

                # Handle both HTML and plain text
                if message.body:
                    email_data["text"] = message.body

                if message.alternatives:
                    for content, mimetype in message.alternatives:
                        if mimetype == "text/html":
                            email_data["html"] = content

                # Send via Resend
                response = resend.Emails.send(email_data)

                if response.get("id"):
                    msg_count += 1
                else:
                    if not self.fail_silently:
                        raise Exception(f"Resend API error: {response}")

            except Exception as e:
                if not self.fail_silently:
                    raise
                # Log the error silently if fail_silently is True
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send email via Resend: {str(e)}")

        return msg_count
