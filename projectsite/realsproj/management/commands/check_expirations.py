from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from realsproj.models import (
    ProductBatches, RawMaterialBatches, 
    ProductInventory, RawMaterialInventory,
    Notifications, Withdrawals, User
)
from datetime import timedelta


class Command(BaseCommand):
    help = "Check for expiring and expired items, create notifications, and auto-withdraw expired items using FEFO"

    def handle(self, *args, **options):
        today = timezone.localdate()
        one_week = today + timedelta(days=7)
        one_month = today + timedelta(days=30)
        
        try:
            system_user = User.objects.filter(is_superuser=True).first()
            if not system_user:
                system_user = User.objects.first()
        except:
            system_user = None
        
        if not system_user:
            self.stdout.write(self.style.ERROR("No user found to create withdrawals"))
            return

        self.stdout.write(self.style.WARNING("Checking expiration dates..."))

        expire_today_count = 0
        expire_week_count = 0
        expire_month_count = 0

        self.stdout.write(self.style.WARNING("\nChecking Product Batches..."))
        
        product_batches = ProductBatches.objects.select_related(
            "product__product_type", "product__variant", "product__size_unit", "product__size"
        ).filter(
            Q(is_expired=False) | Q(is_expired__isnull=True),
            is_archived=False,
            quantity__gt=0
        ).order_by('expiration_date')
        
        for batch in product_batches:
            if not batch.expiration_date:
                continue
                
            product_name = str(batch.product)
            qty = int(batch.quantity)
            exp_date = batch.expiration_date
            
            notification_exists = Notifications.objects.filter(
                item_type="PRODUCT",
                item_id=batch.id,
                notification_type="EXPIRATION_ALERT"
            ).exists()
            
        
            if exp_date <= today:
                if not notification_exists:
                    if qty <= 0 or batch.is_expired == True:
                        continue
                    
                    with transaction.atomic():
                        batch.refresh_from_db()
            
                        if batch.is_expired == True or batch.quantity <= 0:
                            continue

                        expired_qty = int(batch.quantity)
 
                        batch.is_expired = True
                        batch.quantity = 0
                        batch.save(update_fields=['is_expired', 'quantity'])

                        Notifications.objects.create(
                            item_type="PRODUCT",
                            item_id=batch.id,
                            notification_type="EXPIRATION_ALERT",
                            notification_timestamp=timezone.now(),
                            is_read=False
                        )
                        
                        expire_today_count += 1
                        self.stdout.write(self.style.ERROR(
                            f"  EXPIRED TODAY: {expired_qty} {product_name} (Batch #{batch.id}, Exp: {exp_date})"
                        ))

            elif exp_date <= one_week:
                if not notification_exists:
                    Notifications.objects.create(
                        item_type="PRODUCT",
                        item_id=batch.id,
                        notification_type="EXPIRATION_ALERT",
                        notification_timestamp=timezone.now(),
                        is_read=False
                    )
                    expire_week_count += 1
                    days_left = (exp_date - today).days
                    self.stdout.write(self.style.WARNING(
                        f"  EXPIRES IN {days_left} DAY(S): {qty} {product_name} (Batch #{batch.id}, Exp: {exp_date})"
                    ))

            elif exp_date <= one_month:
                if not notification_exists:
                    Notifications.objects.create(
                        item_type="PRODUCT",
                        item_id=batch.id,
                        notification_type="EXPIRATION_ALERT",
                        notification_timestamp=timezone.now(),
                        is_read=False
                    )
                    expire_month_count += 1
                    days_left = (exp_date - today).days
                    self.stdout.write(self.style.WARNING(
                        f"  EXPIRES IN {days_left} DAYS: {qty} {product_name} (Batch #{batch.id}, Exp: {exp_date})"
                    ))
        
        self.stdout.write(self.style.WARNING("\nChecking Raw Material Batches..."))
        
        material_batches = RawMaterialBatches.objects.select_related(
            "material__unit"
        ).filter(
            Q(is_expired=False) | Q(is_expired__isnull=True),
            is_archived=False,
            quantity__gt=0,
            expiration_date__isnull=False
        ).order_by('expiration_date')
        
        for batch in material_batches:
            material_name = batch.material.name
            qty = float(batch.quantity)
            exp_date = batch.expiration_date

            notification_exists = Notifications.objects.filter(
                item_type="RAW_MATERIAL",
                item_id=batch.id,
                notification_type="EXPIRATION_ALERT"
            ).exists()

            if exp_date <= today:
                if not notification_exists:
                    if qty <= 0 or batch.is_expired == True:
                        continue
                    
                    with transaction.atomic():
                        batch.refresh_from_db()
                        
                        if batch.is_expired == True or batch.quantity <= 0:
                            continue

                        expired_qty = float(batch.quantity)

                        batch.is_expired = True
                        batch.quantity = 0
                        batch.save(update_fields=['is_expired', 'quantity'])

                        Notifications.objects.create(
                            item_type="RAW_MATERIAL",
                            item_id=batch.id,
                            notification_type="EXPIRATION_ALERT",
                            notification_timestamp=timezone.now(),
                            is_read=False
                        )
                        
                        expire_today_count += 1
                        self.stdout.write(self.style.ERROR(
                            f"  EXPIRED TODAY: {expired_qty} {material_name} (Batch #{batch.id}, Exp: {exp_date})"
                        ))

            elif exp_date <= one_week:
                if not notification_exists:
                    Notifications.objects.create(
                        item_type="RAW_MATERIAL",
                        item_id=batch.id,
                        notification_type="EXPIRATION_ALERT",
                        notification_timestamp=timezone.now(),
                        is_read=False
                    )
                    expire_week_count += 1
                    days_left = (exp_date - today).days
                    self.stdout.write(self.style.WARNING(
                        f"  EXPIRES IN {days_left} DAY(S): {qty} {material_name} (Batch #{batch.id}, Exp: {exp_date})"
                    ))
            
            elif exp_date <= one_month:
                if not notification_exists:
                    Notifications.objects.create(
                        item_type="RAW_MATERIAL",
                        item_id=batch.id,
                        notification_type="EXPIRATION_ALERT",
                        notification_timestamp=timezone.now(),
                        is_read=False
                    )
                    expire_month_count += 1
                    days_left = (exp_date - today).days
                    self.stdout.write(self.style.WARNING(
                        f"  EXPIRES IN {days_left} DAYS: {qty} {material_name} (Batch #{batch.id}, Exp: {exp_date})"
                    ))
        
     
        self.stdout.write(self.style.SUCCESS("\n" + "="*60))
        self.stdout.write(self.style.SUCCESS("EXPIRATION CHECK COMPLETE"))
        self.stdout.write(self.style.SUCCESS("="*60))
        
        if expire_today_count > 0:
            self.stdout.write(self.style.ERROR(f"{expire_today_count} item(s) expired today (auto-removed from inventory)"))
        
        if expire_week_count > 0:
            self.stdout.write(self.style.WARNING(f"{expire_week_count} item(s) will expire within a week"))
        
        if expire_month_count > 0:
            self.stdout.write(self.style.WARNING(f"{expire_month_count} item(s) will expire within a month"))
        
        if expire_today_count == 0 and expire_week_count == 0 and expire_month_count == 0:
            self.stdout.write(self.style.SUCCESS("No expiring items found"))
        
        self.stdout.write(self.style.SUCCESS("="*60 + "\n"))
