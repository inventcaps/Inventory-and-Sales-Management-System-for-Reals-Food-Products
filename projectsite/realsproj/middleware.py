from django.utils import timezone
from realsproj.models import UserActivity
from django.contrib.auth import logout
from django.shortcuts import redirect


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

        # Check if session has deactivation flag
        if request.session.get('show_deactivated_modal'):
            # Set a flag for the template to show modal
            request.show_deactivated_modal = True
            # DON'T clear the flag yet - let the page load with modal first
        
        # Check if user is authenticated but not active (deactivated)
        # BUT if we need to show the modal, let the page load first
        if request.user.is_authenticated and not request.user.is_active:
            if not hasattr(request, 'show_deactivated_modal'):
                # No modal to show, just logout and redirect
                logout(request)
                return redirect('login')
            # else: Let the page load with the modal, modal will handle logout
        
        response = self.get_response(request)
        return response
