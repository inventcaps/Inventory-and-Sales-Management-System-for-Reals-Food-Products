from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from realsproj.models import Withdrawals, Products, RawMaterials
from decimal import Decimal
from django.utils import timezone

class Command(BaseCommand):
    help = 'Test REPLACEMENT_FOR_RETURNED withdrawal functionality'

    def handle(self, *args, **options):
        try:
            # Get a test user (first superuser)
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                self.stdout.write(self.style.ERROR('No superuser found. Please create a superuser first.'))
                return

            # Get a test product with inventory
            product = Products.objects.select_related('productinventory').first()
            if not product:
                self.stdout.write(self.style.ERROR('No products found in database.'))
                return

            # Check current stock
            current_stock = product.productinventory.total_stock
            self.stdout.write(f'Product: {product}')
            self.stdout.write(f'Current stock: {current_stock}')

            if current_stock < 1:
                self.stdout.write(self.style.ERROR('Product has insufficient stock for testing.'))
                return

            # Test creating a REPLACEMENT_FOR_RETURNED withdrawal
            test_quantity = Decimal('1.0')
            
            self.stdout.write(f'Creating REPLACEMENT_FOR_RETURNED withdrawal for {test_quantity} units...')
            
            withdrawal = Withdrawals.objects.create(
                item_id=product.id,
                item_type="PRODUCT",
                quantity=test_quantity,
                reason="REPLACEMENT_FOR_RETURNED",
                date=timezone.now(),
                created_by_admin=user,
            )
            
            self.stdout.write(self.style.SUCCESS(f'Withdrawal created successfully with ID: {withdrawal.id}'))
            
            # Update inventory
            product.productinventory.total_stock -= test_quantity
            product.productinventory.save()
            
            # Check new stock
            product.productinventory.refresh_from_db()
            new_stock = product.productinventory.total_stock
            self.stdout.write(f'New stock after withdrawal: {new_stock}')
            
            # Verify the withdrawal was saved correctly
            saved_withdrawal = Withdrawals.objects.get(id=withdrawal.id)
            self.stdout.write(f'Saved withdrawal reason: {saved_withdrawal.reason}')
            self.stdout.write(f'Saved withdrawal quantity: {saved_withdrawal.quantity}')
            
            # Check if it appears in financial loss query
            financial_loss_withdrawals = Withdrawals.objects.filter(
                reason__in=['EXPIRED', 'DAMAGED', 'REPLACEMENT_FOR_RETURNED'],
                is_archived=False,
                id=withdrawal.id
            )
            
            if financial_loss_withdrawals.exists():
                self.stdout.write(self.style.SUCCESS('✅ Withdrawal correctly appears in financial loss query'))
            else:
                self.stdout.write(self.style.ERROR('❌ Withdrawal does NOT appear in financial loss query'))
            
            self.stdout.write(self.style.SUCCESS('Test completed successfully!'))
            
        except Exception as e:
            import traceback
            self.stdout.write(self.style.ERROR(f'Error during test: {str(e)}'))
            self.stdout.write(self.style.ERROR(f'Traceback: {traceback.format_exc()}'))
