"""
Custom email backend for SendGrid email service.
Uses HTTP API instead of SMTP to work on Railway.
"""
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import logging

logger = logging.getLogger(__name__)


class SendGridBackend(BaseEmailBackend):
    """
    Email backend that uses SendGrid HTTP API for sending emails.
    Works on Railway where SMTP ports are blocked.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = settings.SENDGRID_API_KEY
        self.client = SendGridAPIClient(self.api_key) if self.api_key else None

    def send_messages(self, email_messages):
        """
        Send one or more EmailMessage objects and return the number of email
        messages sent.
        """
        if not self.api_key or not self.client:
            if not self.fail_silently:
                raise ValueError("SENDGRID_API_KEY is not set")
            return 0

        msg_count = 0
        for message in email_messages:
            try:
                # Create SendGrid Mail object
                mail = Mail(
                    from_email=message.from_email,
                    to_emails=message.to,
                    subject=message.subject,
                    plain_text_content=message.body,
                )

                # Handle HTML content if present
                if message.alternatives:
                    for content, mimetype in message.alternatives:
                        if mimetype == "text/html":
                            mail.html_content = content
                            break

                # Send via SendGrid
                response = self.client.send(mail)
                
                # Check if email was sent successfully (status code 202)
                if response.status_code == 202:
                    msg_count += 1
                    logger.info(f"Email sent successfully to {message.to}")
                else:
                    error_msg = f"SendGrid API error: {response.status_code}"
                    if not self.fail_silently:
                        raise Exception(error_msg)
                    logger.error(error_msg)

            except Exception as e:
                error_msg = f"Failed to send email via SendGrid: {str(e)}"
                logger.error(error_msg)
                if not self.fail_silently:
                    raise

        return msg_count
