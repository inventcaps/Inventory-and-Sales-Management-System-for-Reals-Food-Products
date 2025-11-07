from django.core.management.base import BaseCommand
from realsproj.models import UnitPrices, SrpPrices, AuthUser

class Command(BaseCommand):
    help = 'Fix NULL created_by_admin in UnitPrices and SrpPrices tables'

    def handle(self, *args, **options):
        # Get the first superuser to use as default created_by_admin
        try:
            default_admin = AuthUser.objects.filter(is_superuser=True).first()
            if not default_admin:
                self.stdout.write(self.style.ERROR('No superuser found in database'))
                return
            
            # Fix UnitPrices
            unit_prices_null = UnitPrices.objects.filter(created_by_admin__isnull=True)
            unit_count = unit_prices_null.count()
            if unit_count > 0:
                unit_prices_null.update(created_by_admin=default_admin)
                self.stdout.write(self.style.SUCCESS(f'✅ Fixed {unit_count} UnitPrices records'))
            else:
                self.stdout.write(self.style.SUCCESS('✅ No NULL UnitPrices records found'))
            
            # Fix SrpPrices
            srp_prices_null = SrpPrices.objects.filter(created_by_admin__isnull=True)
            srp_count = srp_prices_null.count()
            if srp_count > 0:
                srp_prices_null.update(created_by_admin=default_admin)
                self.stdout.write(self.style.SUCCESS(f'✅ Fixed {srp_count} SrpPrices records'))
            else:
                self.stdout.write(self.style.SUCCESS('✅ No NULL SrpPrices records found'))
            
            self.stdout.write(self.style.SUCCESS(f'\n🎉 Database cleanup complete!'))
            self.stdout.write(self.style.SUCCESS(f'   Total records fixed: {unit_count + srp_count}'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {str(e)}'))
