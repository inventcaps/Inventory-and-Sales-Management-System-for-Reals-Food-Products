from django.utils import timezone
from django.db import connection
from realsproj.models import UserActivity


class UpdateLastActivityMiddleware:
    """
    Middleware to update user's last_activity timestamp on every request.
    This helps track if a user is actively using the system.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                activity, created = UserActivity.objects.get_or_create(user=request.user)
                activity.last_activity = timezone.now()
                activity.save(update_fields=['last_activity'])
            except Exception:
                pass

        response = self.get_response(request)
        return response


class SetCurrentUserMiddleware:
    """
    Middleware to set the current user ID in PostgreSQL session variable
    for use in database triggers for accurate history logging.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                # Set the current user ID in PostgreSQL session variable
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.current_user_id', %s, false)", [str(request.user.id)])
            except Exception:
                pass

        response = self.get_response(request)
        return response
