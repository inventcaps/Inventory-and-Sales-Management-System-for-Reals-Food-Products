import os
import json
import datetime
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core import serializers
from django.db import transaction
from django.apps import apps

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Restore database from Python JSON backup'

    def add_arguments(self, parser):
        parser.add_argument(
            'backup_file',
            help='Name of the backup file to restore (e.g., reals_backup_python_20251111_213011.json)',
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing data before restoring (DANGEROUS!)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be restored without actually doing it',
        )

    def handle(self, *args, **options):
        backup_file = options['backup_file']
        clear_existing = options['clear_existing']
        dry_run = options['dry_run']
        
        # Find backup file
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        backup_path = os.path.join(backup_dir, backup_file)
        
        if not os.path.exists(backup_path):
            self.stdout.write(
                self.style.ERROR(f"❌ Backup file not found: {backup_file}")
            )
            return
        
        try:
            # Load backup data
            self.stdout.write(f"📂 Loading backup file: {backup_file}")
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            # Show backup info
            metadata = backup_data.get('_metadata', {})
            total_records = metadata.get('total_records', 0)
            created_at = metadata.get('created_at', 'Unknown')
            
            self.stdout.write(f"📊 Backup created: {created_at}")
            self.stdout.write(f"📋 Total records: {total_records:,}")
            self.stdout.write("-" * 60)
            
            # Show what will be restored
            models_to_restore = []
            for model_name, model_data in backup_data.items():
                if model_name != '_metadata':
                    count = model_data.get('count', 0)
                    models_to_restore.append((model_name, count))
                    self.stdout.write(f"  📦 {model_name}: {count} records")
            
            if dry_run:
                self.stdout.write(
                    self.style.WARNING("\n🔍 DRY RUN - No data will be restored")
                )
                return
            
            # Confirm restoration
            if not clear_existing:
                self.stdout.write(
                    self.style.WARNING(
                        "\n⚠️  This will ADD data to existing records. "
                        "Use --clear-existing to replace all data."
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        "\n🚨 WARNING: This will DELETE ALL existing data and replace it!"
                    )
                )
            
            confirm = input("\nDo you want to continue? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write("❌ Restoration cancelled")
                return
            
            # Start restoration
            self.stdout.write(f"\n🔄 Starting restoration...")
            
            with transaction.atomic():
                restored_count = 0
                
                # Clear existing data if requested
                if clear_existing:
                    self.stdout.write("🗑️  Clearing existing data...")
                    for model_name, _ in models_to_restore:
                        try:
                            app_label, model_name_only = model_name.split('.')
                            model_class = apps.get_model(app_label, model_name_only)
                            deleted_count = model_class.objects.all().delete()[0]
                            self.stdout.write(f"  🗑️  Cleared {model_name}: {deleted_count} records")
                        except Exception as e:
                            self.stdout.write(f"  ⚠️  Could not clear {model_name}: {e}")
                
                # Restore data
                for model_name, model_data in backup_data.items():
                    if model_name == '_metadata':
                        continue
                    
                    try:
                        data_string = model_data.get('data', '[]')
                        count = model_data.get('count', 0)
                        
                        if count > 0:
                            self.stdout.write(f"📥 Restoring {model_name}...")
                            
                            # Deserialize and save objects
                            objects = serializers.deserialize('json', data_string)
                            saved_count = 0
                            
                            for obj in objects:
                                try:
                                    obj.save()
                                    saved_count += 1
                                except Exception as e:
                                    self.stdout.write(f"    ⚠️  Error saving record: {e}")
                            
                            self.stdout.write(f"  ✅ Restored {saved_count}/{count} records")
                            restored_count += saved_count
                        
                    except Exception as e:
                        self.stdout.write(f"  ❌ Failed to restore {model_name}: {e}")
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n🎉 Restoration completed! Restored {restored_count:,} records"
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Restoration failed: {str(e)}")
            )
            logger.error(f"Restoration failed: {e}")

    def get_available_backups(self):
        """List available backup files"""
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        if not os.path.exists(backup_dir):
            return []
        
        backups = []
        for filename in os.listdir(backup_dir):
            if filename.startswith('reals_backup_python_') and filename.endswith('.json'):
                backups.append(filename)
        
        return sorted(backups, reverse=True)  # Newest first
