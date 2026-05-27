import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils import timezone
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from .models import UserActivity, HistoryLog, HistoryLogTypes

logger = logging.getLogger(__name__)

@receiver(user_logged_in)
def user_logged_in_handler(sender, request, user, **kwargs):
    activity, created = UserActivity.objects.get_or_create(user=user)
    user.last_login = timezone.now()
    user.save()

@receiver(user_logged_out)
def user_logged_out_handler(sender, request, user, **kwargs):
    if user and user.is_authenticated:
        activity, created = UserActivity.objects.get_or_create(user=user)
        activity.last_logout = timezone.now()
        activity.save()

@receiver(post_save, sender=User)
def user_registered_handler(sender, instance, created, **kwargs):
    if created:
        try:
            first_admin = User.objects.filter(is_superuser=True).first()
            if not first_admin:
                first_admin = instance

            log_type, _ = HistoryLogTypes.objects.get_or_create(
                category="User Sign Up",
                defaults={'created_by_admin_id': first_admin.id}
            )

            HistoryLog.objects.create(
                admin_id=instance.id,
                log_type_id=log_type.id,
                log_date=timezone.now(),
                entity_type="user",
                entity_id=instance.id,
                details={
                    "after": {
                        "username": instance.username,
                        "email": instance.email,
                        "first_name": instance.first_name,
                        "last_name": instance.last_name,
                        "date_joined": instance.date_joined.isoformat() if instance.date_joined else None
                    }
                },
                is_archived=False
            )
            logger.info("History log created for user: %s", instance.username)
        except Exception as e:
            logger.error("Error creating history log for user %s: %s", instance.username, str(e))
            import traceback
            traceback.print_exc()
