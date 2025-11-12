import schedule
import time
import subprocess
import os
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Start automatic backup scheduler'

    def add_arguments(self, parser):
        parser.add_argument(
            '--time',
            default='02:00',
            help='Time to run daily backup (format: HH:MM, default: 02:00)',
        )
        parser.add_argument(
            '--interval',
            choices=['daily', 'hourly', 'weekly'],
            default='daily',
            help='Backup interval (default: daily)',
        )

    def handle(self, *args, **options):
        backup_time = options['time']
        interval = options['interval']
        
        self.stdout.write(f"🚀 Starting backup scheduler...")
        self.stdout.write(f"⏰ Schedule: {interval} at {backup_time}")
        self.stdout.write(f"📧 Email notifications: Enabled")
        self.stdout.write(f"🛑 Press Ctrl+C to stop")
        
        # Schedule the backup
        if interval == 'daily':
            schedule.every().day.at(backup_time).do(self.run_backup)
        elif interval == 'hourly':
            schedule.every().hour.do(self.run_backup)
        elif interval == 'weekly':
            schedule.every().week.at(backup_time).do(self.run_backup)
        
        # Run the scheduler
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n🛑 Backup scheduler stopped"))

    def run_backup(self):
        """Execute the backup command"""
        try:
            self.stdout.write(f"🔄 Running scheduled backup at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Change to project directory
            project_dir = settings.BASE_DIR
            manage_py = os.path.join(project_dir, 'manage.py')
            
            # Run backup command
            result = subprocess.run([
                'python', 
                manage_py, 
                'backup_database_python', 
                '--email-notification'
            ], cwd=project_dir, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS("✅ Scheduled backup completed successfully"))
            else:
                self.stdout.write(self.style.ERROR(f"❌ Scheduled backup failed: {result.stderr}"))
                logger.error(f"Scheduled backup failed: {result.stderr}")
                
        except Exception as e:
            error_msg = f"❌ Scheduled backup error: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg)
