import os
import subprocess
import datetime
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Create automatic database backup from Supabase'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email-notification',
            action='store_true',
            help='Send email notification after backup',
        )

    def handle(self, *args, **options):
        try:
            # Get database settings
            db_settings = settings.DATABASES['default']
            
            # Create backup filename with timestamp
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"reals_backup_{timestamp}.sql"
            
            # Create backups directory if it doesn't exist
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Create pg_dump command for Supabase
            dump_command = [
                'pg_dump',
                f"--host={db_settings['HOST']}",
                f"--port={db_settings.get('PORT', '5432')}",
                f"--username={db_settings['USER']}",
                f"--dbname={db_settings['NAME']}",
                '--verbose',
                '--clean',
                '--no-owner',
                '--no-privileges',
                f"--file={backup_path}"
            ]
            
            # Set password environment variable
            env = os.environ.copy()
            env['PGPASSWORD'] = db_settings['PASSWORD']
            
            # Execute backup
            self.stdout.write(f"🔄 Creating backup from Supabase: {backup_filename}")
            self.stdout.write(f"📡 Host: {db_settings['HOST']}")
            
            result = subprocess.run(dump_command, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Check if file was created and has content
                if os.path.exists(backup_path) and os.path.getsize(backup_path) > 0:
                    file_size = os.path.getsize(backup_path) / (1024 * 1024)  # Size in MB
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ Successfully created backup: {backup_filename} ({file_size:.2f} MB)'
                        )
                    )
                    
                    # Send email notification if requested
                    if options['email_notification']:
                        self.send_notification(backup_filename, True, file_size)
                        
                    # Cleanup old backups (keep last 7 days)
                    self.cleanup_old_backups()
                else:
                    error_msg = "❌ Backup file was not created or is empty"
                    self.stdout.write(self.style.ERROR(error_msg))
                    
            else:
                error_msg = f"❌ Backup failed: {result.stderr}"
                self.stdout.write(self.style.ERROR(error_msg))
                logger.error(error_msg)
                
                if options['email_notification']:
                    self.send_notification(backup_filename, False, 0, error_msg)
                    
        except Exception as e:
            error_msg = f"❌ Backup process failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg)
            
            if options['email_notification']:
                self.send_notification("", False, 0, error_msg)

    def send_notification(self, filename, success, file_size=0, error_msg=""):
        """Send email notification about backup status"""
        try:
            if success:
                subject = f"✅ Supabase Backup Successful - {filename}"
                message = f"""
🎉 Database backup completed successfully!

📁 File: {filename}
📊 Size: {file_size:.2f} MB
⏰ Time: {datetime.datetime.now()}
🗄️ Database: {settings.DATABASES['default']['HOST']}
                """
            else:
                subject = "❌ Supabase Backup Failed"
                message = f"""
⚠️ Database backup failed!

❌ Error: {error_msg}
⏰ Time: {datetime.datetime.now()}
🗄️ Database: {settings.DATABASES['default']['HOST']}
                """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [settings.EMAIL_HOST_USER],  # Send to admin email
                fail_silently=False,
            )
            
            self.stdout.write(self.style.SUCCESS("📧 Email notification sent"))
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️ Failed to send notification email: {e}"))

    def cleanup_old_backups(self):
        """Remove backups older than 7 days"""
        try:
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            if not os.path.exists(backup_dir):
                return
                
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=7)
            cleaned_count = 0
            
            for filename in os.listdir(backup_dir):
                if filename.startswith('reals_backup_') and filename.endswith('.sql'):
                    file_path = os.path.join(backup_dir, filename)
                    file_time = datetime.datetime.fromtimestamp(os.path.getctime(file_path))
                    
                    if file_time < cutoff_date:
                        os.remove(file_path)
                        cleaned_count += 1
                        self.stdout.write(f"🗑️ Removed old backup: {filename}")
            
            if cleaned_count > 0:
                self.stdout.write(self.style.SUCCESS(f"🧹 Cleaned up {cleaned_count} old backup(s)"))
                        
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")