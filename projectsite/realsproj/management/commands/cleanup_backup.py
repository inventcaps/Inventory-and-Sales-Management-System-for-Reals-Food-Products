import os
import datetime
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.conf import settings
from realsproj.utils.backup_manager import backup_manager

class Command(BaseCommand):
    help = 'Cleanup old backup files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to keep backups (default: 7)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        days_to_keep = options['days']
        dry_run = options['dry_run']
        
        self.stdout.write(f"🧹 Cleaning up backups older than {days_to_keep} days...")
        
        try:
            backup_dir = backup_manager.backup_dir
            
            if not os.path.exists(backup_dir):
                self.stdout.write(
                    self.style.WARNING("⚠️ Backup directory does not exist")
                )
                return
            
            cutoff_date = timezone.now() - datetime.timedelta(days=days_to_keep)
            files_to_delete = []
            total_size = 0
            
            # Find files to delete
            for filename in os.listdir(backup_dir):
                if filename.startswith('reals_backup_') and filename.endswith('.sql'):
                    file_path = os.path.join(backup_dir, filename)
                    file_time = datetime.datetime.fromtimestamp(os.path.getctime(file_path))
                    
                    if file_time < cutoff_date:
                        file_size = os.path.getsize(file_path)
                        files_to_delete.append({
                            'filename': filename,
                            'path': file_path,
                            'created': file_time,
                            'size': file_size
                        })
                        total_size += file_size
            
            if not files_to_delete:
                self.stdout.write(
                    self.style.SUCCESS("✅ No old backup files found to cleanup")
                )
                return
            
            # Show what will be deleted
            self.stdout.write(f"\n📋 Found {len(files_to_delete)} old backup(s) to cleanup:")
            self.stdout.write("-" * 80)
            
            for file_info in files_to_delete:
                size_mb = file_info['size'] / (1024 * 1024)
                self.stdout.write(
                    f"🗑️  {file_info['filename']} "
                    f"({size_mb:.2f} MB) - Created: {file_info['created'].strftime('%Y-%m-%d %H:%M:%S')}"
                )
            
            total_size_mb = total_size / (1024 * 1024)
            self.stdout.write("-" * 80)
            self.stdout.write(f"💾 Total space to be freed: {total_size_mb:.2f} MB")
            
            if dry_run:
                self.stdout.write(
                    self.style.WARNING("\n🔍 DRY RUN - No files were actually deleted")
                )
                return
            
            # Actually delete the files
            deleted_count = 0
            for file_info in files_to_delete:
                try:
                    os.remove(file_info['path'])
                    deleted_count += 1
                    self.stdout.write(f"✅ Deleted: {file_info['filename']}")
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"❌ Failed to delete {file_info['filename']}: {e}")
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n🎉 Cleanup completed! Deleted {deleted_count} backup file(s), "
                    f"freed {total_size_mb:.2f} MB of space"
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Cleanup failed: {str(e)}")
            )