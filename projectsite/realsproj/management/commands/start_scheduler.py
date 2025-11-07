from django.core.management.base import BaseCommand
from realsproj.scheduler import start_scheduler
import time


class Command(BaseCommand):
    help = "Manually start the expiration check scheduler"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting expiration scheduler..."))
        start_scheduler()
        self.stdout.write(self.style.SUCCESS("Scheduler started successfully"))
        self.stdout.write(self.style.WARNING("Scheduled to run daily at 00:00 (midnight)"))
        self.stdout.write(self.style.WARNING("Scheduler is running in the background..."))
        self.stdout.write(self.style.WARNING("Press Ctrl+C to stop"))
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nStopping scheduler..."))
