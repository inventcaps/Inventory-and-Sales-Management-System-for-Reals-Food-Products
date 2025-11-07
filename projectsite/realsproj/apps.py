from django.apps import AppConfig

class RealsprojConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'realsproj'
    
    def ready(self):
        import realsproj.signals
        
        # Expiration checks are now handled by Supabase pg_cron
        # No need for APScheduler anymore
