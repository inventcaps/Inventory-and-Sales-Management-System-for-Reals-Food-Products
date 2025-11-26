import requests
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings
from decouple import config


class MailgunBackend(BaseEmailBackend):
    """
    Custom email backend using Mailgun HTTP API to bypass SMTP restrictions
    """
    
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = config('MAILGUN_API_KEY', default='')
        self.domain = config('MAILGUN_DOMAIN', default='')
        
    def send_messages(self, email_messages):
        """
        Send email messages using Mailgun API
        """
        if not self.api_key or not self.domain:
            if not self.fail_silently:
                raise Exception("Mailgun API key or domain not configured")
            return 0
            
        sent_count = 0
        for message in email_messages:
            try:
                response = requests.post(
                    f"https://api.mailgun.net/v3/{self.domain}/messages",
                    auth=("api", self.api_key),
                    data={
                        "from": message.from_email,
                        "to": message.to,
                        "subject": message.subject,
                        "text": message.body,
                        "html": getattr(message, 'alternatives', [{}])[0].get('content', '') if hasattr(message, 'alternatives') else ''
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    sent_count += 1
                elif not self.fail_silently:
                    raise Exception(f"Mailgun API error: {response.status_code} - {response.text}")
                    
            except Exception as e:
                if not self.fail_silently:
                    raise e
                    
        return sent_count


class FallbackEmailBackend(BaseEmailBackend):
    """
    Fallback email backend that tries Mailgun first, then console
    """
    
    def send_messages(self, email_messages):
        # Try Mailgun first
        mailgun_key = config('MAILGUN_API_KEY', default='')
        mailgun_domain = config('MAILGUN_DOMAIN', default='')
        
        if mailgun_key and mailgun_domain:
            try:
                backend = MailgunBackend(fail_silently=True)
                return backend.send_messages(email_messages)
            except:
                pass
        
        # Fallback to console backend
        from django.core.mail.backends.console import EmailBackend as ConsoleBackend
        console_backend = ConsoleBackend()
        return console_backend.send_messages(email_messages)
