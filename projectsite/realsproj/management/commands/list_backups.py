import os
import json
import datetime
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'List available backup files'

    def handle(self, *args, **options):
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        
        if not os.path.exists(backup_dir):
            self.stdout.write(
                self.style.WARNING("⚠️ No backup directory found")
            )
            return
        
        # Find backup files
        backups = []
        for filename in os.listdir(backup_dir):
            if filename.startswith('reals_backup_python_') and filename.endswith('.json'):
                file_path = os.path.join(backup_dir, filename)
                file_stats = os.stat(file_path)
                
                # Try to read metadata
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        backup_data = json.load(f)
                    metadata = backup_data.get('_metadata', {})
                    total_records = metadata.get('total_records', 0)
                    created_at = metadata.get('created_at', 'Unknown')
                except Exception:
                    total_records = 0
                    created_at = 'Unknown'
                
                backups.append({
                    'filename': filename,
                    'size_mb': file_stats.st_size / (1024 * 1024),
                    'created_at': datetime.datetime.fromtimestamp(file_stats.st_ctime),
                    'total_records': total_records,
                    'backup_created_at': created_at
                })
        
        if not backups:
            self.stdout.write(
                self.style.WARNING("⚠️ No backup files found")
            )
            return
        
        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        
        self.stdout.write(f"📁 Found {len(backups)} backup file(s):")
        self.stdout.write("=" * 80)
        
        for i, backup in enumerate(backups, 1):
            self.stdout.write(f"\n{i}. 📄 {backup['filename']}")
            self.stdout.write(f"   📊 Size: {backup['size_mb']:.2f} MB")
            self.stdout.write(f"   📋 Records: {backup['total_records']:,}")
            self.stdout.write(f"   📅 File Created: {backup['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")
            self.stdout.write(f"   🗄️  Backup Created: {backup['backup_created_at']}")
        
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("💡 To restore a backup, use:")
        self.stdout.write("   python manage.py restore_database_python <filename>")
        self.stdout.write("\n💡 To see what would be restored (dry run):")
        self.stdout.write("   python manage.py restore_database_python <filename> --dry-run")
