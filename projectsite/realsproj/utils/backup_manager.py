import os
import shutil
import datetime
import subprocess
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

class BackupManager:
    """Utility class for managing database backups"""
    
    def __init__(self):
        self.backup_dir = getattr(settings, 'BACKUP_DIR', os.path.join(settings.BASE_DIR, 'backups'))
        self.keep_days = getattr(settings, 'BACKUP_KEEP_DAYS', 7)
        
    def ensure_backup_directory(self):
        """Ensure backup directory exists"""
        os.makedirs(self.backup_dir, exist_ok=True)
        return self.backup_dir
    
    def get_backup_filename(self, prefix="reals_backup"):
        """Generate backup filename with timestamp"""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{prefix}_{timestamp}.sql"
    
    def create_backup(self, email_notification=False):
        """Create a database backup"""
        try:
            self.ensure_backup_directory()
            
            # Get database settings
            db_settings = settings.DATABASES['default']
            backup_filename = self.get_backup_filename()
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Create pg_dump command
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
            logger.info(f"Creating backup: {backup_filename}")
            result = subprocess.run(dump_command, env=env, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(backup_path) and os.path.getsize(backup_path) > 0:
                file_size = os.path.getsize(backup_path) / (1024 * 1024)  # Size in MB
                logger.info(f"✅ Backup created successfully: {backup_filename} ({file_size:.2f} MB)")
                
                if email_notification:
                    self.send_backup_notification(backup_filename, True, file_size)
                
                # Cleanup old backups
                self.cleanup_old_backups()
                
                return {
                    'success': True,
                    'filename': backup_filename,
                    'size_mb': file_size,
                    'path': backup_path
                }
            else:
                error_msg = f"Backup failed: {result.stderr}"
                logger.error(error_msg)
                
                if email_notification:
                    self.send_backup_notification(backup_filename, False, 0, error_msg)
                
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            error_msg = f"Backup process failed: {str(e)}"
            logger.error(error_msg)
            
            if email_notification:
                self.send_backup_notification("", False, 0, error_msg)
            
            return {
                'success': False,
                'error': error_msg
            }
    
    def restore_backup(self, backup_filename):
        """Restore database from backup file"""
        try:
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            if not os.path.exists(backup_path):
                return {
                    'success': False,
                    'error': f"Backup file not found: {backup_filename}"
                }
            
            # Get database settings
            db_settings = settings.DATABASES['default']
            
            # Create psql restore command
            restore_command = [
                'psql',
                f"--host={db_settings['HOST']}",
                f"--port={db_settings.get('PORT', '5432')}",
                f"--username={db_settings['USER']}",
                f"--dbname={db_settings['NAME']}",
                f"--file={backup_path}"
            ]
            
            # Set password environment variable
            env = os.environ.copy()
            env['PGPASSWORD'] = db_settings['PASSWORD']
            
            # Execute restore
            logger.info(f"Restoring backup: {backup_filename}")
            result = subprocess.run(restore_command, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"✅ Backup restored successfully: {backup_filename}")
                return {
                    'success': True,
                    'filename': backup_filename
                }
            else:
                error_msg = f"Restore failed: {result.stderr}"
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            error_msg = f"Restore process failed: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
    
    def list_backups(self):
        """List all available backup files"""
        try:
            if not os.path.exists(self.backup_dir):
                return []
            
            backups = []
            for filename in os.listdir(self.backup_dir):
                if filename.startswith('reals_backup_') and filename.endswith('.sql'):
                    file_path = os.path.join(self.backup_dir, filename)
                    file_stats = os.stat(file_path)
                    
                    backups.append({
                        'filename': filename,
                        'size_mb': file_stats.st_size / (1024 * 1024),
                        'created_at': datetime.datetime.fromtimestamp(file_stats.st_ctime),
                        'path': file_path
                    })
            
            # Sort by creation time (newest first)
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return []
    
    def cleanup_old_backups(self):
        """Remove backups older than specified days"""
        try:
            if not os.path.exists(self.backup_dir):
                return 0
                
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=self.keep_days)
            cleaned_count = 0
            
            for filename in os.listdir(self.backup_dir):
                if filename.startswith('reals_backup_') and filename.endswith('.sql'):
                    file_path = os.path.join(self.backup_dir, filename)
                    file_time = datetime.datetime.fromtimestamp(os.path.getctime(file_path))
                    
                    if file_time < cutoff_date:
                        os.remove(file_path)
                        cleaned_count += 1
                        logger.info(f"🗑️ Removed old backup: {filename}")
            
            if cleaned_count > 0:
                logger.info(f"🧹 Cleaned up {cleaned_count} old backup(s)")
            
            return cleaned_count
                        
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return 0
    
    def get_backup_stats(self):
        """Get backup statistics"""
        try:
            backups = self.list_backups()
            
            if not backups:
                return {
                    'total_backups': 0,
                    'total_size_mb': 0,
                    'latest_backup': None,
                    'oldest_backup': None
                }
            
            total_size = sum(backup['size_mb'] for backup in backups)
            
            return {
                'total_backups': len(backups),
                'total_size_mb': total_size,
                'latest_backup': backups[0] if backups else None,
                'oldest_backup': backups[-1] if backups else None,
                'backups': backups
            }
            
        except Exception as e:
            logger.error(f"Failed to get backup stats: {e}")
            return {}
    
    def send_backup_notification(self, filename, success, file_size=0, error_msg=""):
        """Send email notification about backup status"""
        try:
            if success:
                subject = f"✅ Database Backup Successful - {filename}"
                message = f"""
🎉 Database backup completed successfully!

📁 File: {filename}
📊 Size: {file_size:.2f} MB
⏰ Time: {timezone.now()}
🗄️ Database: {settings.DATABASES['default']['HOST']}
📂 Location: {self.backup_dir}

This backup will be automatically cleaned up after {self.keep_days} days.
                """
            else:
                subject = "❌ Database Backup Failed"
                message = f"""
⚠️ Database backup failed!

❌ Error: {error_msg}
⏰ Time: {timezone.now()}
🗄️ Database: {settings.DATABASES['default']['HOST']}

Please check the system logs for more details.
                """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [settings.EMAIL_HOST_USER],
                fail_silently=False,
            )
            
            logger.info("📧 Backup notification email sent")
            
        except Exception as e:
            logger.error(f"Failed to send backup notification: {e}")

# Singleton instance
backup_manager = BackupManager()