import os
import json
import datetime
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail import send_mail
from django.core import serializers
from django.apps import apps

logger = logging.getLogger('backup')

class Command(BaseCommand):
    help = 'Create database backup using Django serialization (no pg_dump required)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email-notification',
            action='store_true',
            help='Send email notification after backup',
        )
        parser.add_argument(
            '--format',
            default='json',
            choices=['json', 'xml'],
            help='Backup format (default: json)',
        )

    def handle(self, *args, **options):
        try:
            # Create backup filename with timestamp
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            format_ext = options['format']
            backup_filename = f"reals_backup_python_{timestamp}.{format_ext}"
            
            # Create backups directory if it doesn't exist
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, backup_filename)
            
            logger.info(f"Starting backup process: {backup_filename}")
            logger.info(f"Target database: {settings.DATABASES['default']['HOST']}")
            
            self.stdout.write(f"🔄 Creating Python-based backup: {backup_filename}")
            self.stdout.write(f"📡 Host: {settings.DATABASES['default']['HOST']}")
            
            # Get all models from your app
            app_models = apps.get_app_config('realsproj').get_models()
            
            backup_data = {}
            total_records = 0
            
            # Serialize each model
            for model in app_models:
                model_name = model._meta.label
                try:
                    queryset = model.objects.all()
                    count = queryset.count()
                    
                    if count > 0:
                        serialized_data = serializers.serialize(format_ext, queryset)
                        backup_data[model_name] = {
                            'count': count,
                            'data': serialized_data
                        }
                        total_records += count
                        self.stdout.write(f"  📋 {model_name}: {count} records")
                    
                except Exception as e:
                    self.stdout.write(f"  ⚠️ Skipped {model_name}: {str(e)}")
            
            # Add metadata
            backup_data['_metadata'] = {
                'created_at': datetime.datetime.now().isoformat(),
                'django_version': '5.2',
                'total_records': total_records,
                'database_host': settings.DATABASES['default']['HOST'],
                'backup_type': 'python_serialization'
            }
            
            # Write backup file
            with open(backup_path, 'w', encoding='utf-8') as f:
                if format_ext == 'json':
                    json.dump(backup_data, f, indent=2, ensure_ascii=False)
                else:  # xml
                    # For XML, we'll write a simple structure
                    f.write('<?xml version="1.0" encoding="utf-8"?>\n<backup>\n')
                    for model_name, model_data in backup_data.items():
                        if model_name != '_metadata':
                            f.write(f'  <model name="{model_name}" count="{model_data["count"]}">\n')
                            f.write(f'    {model_data["data"]}\n')
                            f.write('  </model>\n')
                    f.write('</backup>\n')
            
            # Check if file was created successfully
            if os.path.exists(backup_path) and os.path.getsize(backup_path) > 0:
                file_size = os.path.getsize(backup_path) / (1024 * 1024)  # Size in MB
                
                logger.info(f"Backup completed successfully: {backup_filename}")
                logger.info(f"File size: {file_size:.2f} MB, Records: {total_records}")
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Successfully created backup: {backup_filename} ({file_size:.2f} MB)'
                    )
                )
                self.stdout.write(f'📊 Total records backed up: {total_records}')
                
                # Send email notification if requested
                if options['email_notification']:
                    self.send_notification(backup_filename, True, file_size, total_records)
                    
                # Cleanup old backups (keep last 7 days)
                self.cleanup_old_backups()
                
            else:
                error_msg = "❌ Backup file was not created or is empty"
                logger.error(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))
                
        except Exception as e:
            error_msg = f"❌ Backup process failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg)
            
            if options['email_notification']:
                self.send_notification("", False, 0, 0, error_msg)

    def send_notification(self, filename, success, file_size=0, record_count=0, error_msg=""):
        """Send email notification about backup status"""
        try:
            if success:
                subject = f"✅ Python Backup Successful - {filename}"
                message = f"""
🎉 Database backup completed successfully using Python serialization!

📁 File: {filename}
📊 Size: {file_size:.2f} MB
📋 Records: {record_count:,}
⏰ Time: {datetime.datetime.now()}
🗄️ Database: {settings.DATABASES['default']['HOST']}
🐍 Method: Django Serialization (Python-based)
                """
            else:
                subject = "❌ Python Backup Failed"
                message = f"""
⚠️ Database backup failed!

❌ Error: {error_msg}
⏰ Time: {datetime.datetime.now()}
🗄️ Database: {settings.DATABASES['default']['HOST']}
                """
            
            # Get admin email(s) from settings
            admin_emails = getattr(settings, 'ADMIN_EMAILS', [settings.EMAIL_HOST_USER])
            if isinstance(admin_emails, str):
                admin_emails = [admin_emails]
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                admin_emails,  # Send to configured admin email(s)
                fail_silently=False,
            )
            
            self.stdout.write(self.style.SUCCESS("📧 Email notification sent"))
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️ Failed to send notification email: {e}"))

    def cleanup_old_backups(self):
        """Remove backups older than 4 weeks (28 days) for weekly backups"""
        try:
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            if not os.path.exists(backup_dir):
                return
                
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=28)  # Keep 4 weeks of weekly backups
            cleaned_count = 0
            
            for filename in os.listdir(backup_dir):
                if filename.startswith('reals_backup_python_') and (filename.endswith('.json') or filename.endswith('.xml')):
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
