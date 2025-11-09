# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from decimal import Decimal
from django.db.models import Sum
from django.db.models import Q
from datetime import timedelta
from django.utils.safestring import mark_safe
import json
from django.utils import timezone
from django.conf import settings


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.BooleanField()
    is_active = models.BooleanField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'

    def __str__(self):
        return self.username


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.SmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class Expenses(models.Model):
    id = models.BigAutoField(primary_key=True)
    category = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    description = models.TextField(blank=True, null=True)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)
    is_archived = models.BooleanField(default=False) 

    class Meta:
        managed = False
        db_table = 'expenses'

    def __str__(self):
        return f"{self.category} - ₱{self.amount} on {self.date.strftime('%Y-%m-%d')}"


class ExpensesSummary(models.Model):
    id = models.BigIntegerField(primary_key=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'expenses_summary'


class HistoryLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    admin = models.ForeignKey(AuthUser, models.DO_NOTHING)
    log_type = models.ForeignKey('HistoryLogTypes', models.DO_NOTHING)
    log_date = models.DateTimeField(default=timezone.now)
    entity_type = models.CharField(max_length=50)
    entity_id = models.BigIntegerField()
    details = models.JSONField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'history_log'

    def get_entity_display(self):
        try:
            if self.entity_type == "product":
                p = Products.objects.select_related(
                    "product_type", "variant", "size_unit", "size"
                ).get(pk=self.entity_id)
                return f"{p.product_type.name} - {p.variant.name} ({p.size.size_label if p.size else ''} {p.size_unit.unit_name})"

            elif self.entity_type == "raw_material":
                rm = RawMaterials.objects.select_related("unit").get(pk=self.entity_id)
                return f"{rm.name} ({rm.unit.unit_name}) - ₱{rm.price_per_unit}"

            elif self.entity_type == "product_batch":
                pb = ProductBatches.objects.select_related(
                    "product__product_type", "product__variant", "product__size", "product__size_unit"
                ).get(pk=self.entity_id)
                return f"{pb.product.product_type.name} - {pb.product.variant.name} ({pb.product.size.size_label if pb.product.size else ''} {pb.product.size_unit.unit_name})"

            elif self.entity_type == "raw_material_batch":
                rb = RawMaterialBatches.objects.select_related("material").get(pk=self.entity_id)
                return f"{rb.material.name}"

            elif self.entity_type == "expense":
                e = Expenses.objects.get(pk=self.entity_id)
                return f"{e.category}"

            elif self.entity_type == "sale":
                s = Sales.objects.get(pk=self.entity_id)
                # Format category to title case (e.g., ORDER -> Order)
                category = s.category.replace('_', ' ').title() if s.category else s.category
                return f"{category}"

            elif self.entity_type == "withdrawal":
                try:
                    w = Withdrawals.objects.get(pk=self.entity_id)
                    return f"{w.get_reason_display()} - {w.quantity} {w.get_item_type_display()} ({w.get_sales_channel_display() or 'N/A'})"
                except Withdrawals.DoesNotExist:
                    # If withdrawal is deleted, use data from history log details
                    if self.details and 'before' in self.details:
                        data = self.details['before']
                        reason = dict(Withdrawals.REASON_CHOICES).get(data.get('reason'), data.get('reason', 'Unknown'))
                        item_type = dict(Withdrawals.ITEM_TYPE_CHOICES).get(data.get('item_type'), data.get('item_type', 'Unknown'))
                        quantity = data.get('quantity', 'Unknown')
                        return f"{reason} - {quantity} {item_type} (Deleted)"
                    return f"Deleted Withdrawal #{self.entity_id}"

            elif self.entity_type == "product_recipe":
                pr = ProductRecipes.objects.select_related(
                    "product__product_type",
                    "product__variant",
                    "product__size_unit",
                    "product__size",
                    "material"
                ).get(pk=self.entity_id)
                return f"{pr.product.product_type.name} - {pr.product.variant.name} ({pr.product.size.size_label if pr.product.size else ''} {pr.product.size_unit.unit_name})"

            elif self.entity_type == "product_type":
                pt = ProductTypes.objects.get(pk=self.entity_id)
                return pt.name

            elif self.entity_type == "product_variant":
                pv = ProductVariants.objects.get(pk=self.entity_id)
                return pv.name

            elif self.entity_type == "size":
                sz = Sizes.objects.get(pk=self.entity_id)
                return sz.size_label

            elif self.entity_type == "size_unit":
                su = SizeUnits.objects.get(pk=self.entity_id)
                return f"Size Unit: {su.unit_name}"

            elif self.entity_type == "unit_price":
                up = UnitPrices.objects.get(pk=self.entity_id)
                return f"Unit Price: ₱{up.unit_price}"

            elif self.entity_type == "srp_price":
                sp = SrpPrices.objects.get(pk=self.entity_id)
                return f"SRP Price: ₱{sp.srp_price}"

            elif self.entity_type == "user":
                u = AuthUser.objects.get(pk=self.entity_id)
                full_name = f"{u.first_name} {u.last_name}".strip()
                return f"{u.username}" + (f" ({full_name})" if full_name else "")

            else:
                return f"Entity #{self.entity_id}"

        except Exception:
            # Check log type category for better context
            log_category = self.log_type.category.lower() if self.log_type else ""
            
            if "delete" in log_category or "deleted" in log_category:
                # Try to get entity info from details
                if self.details and 'before' in self.details:
                    before_data = self.details['before']

                    if self.entity_type == "product":
                        try:
                            product_type = before_data.get('product_type_id', '')
                            variant = before_data.get('variant_id', '')
                            size = before_data.get('size_id', '')
                            size_unit = before_data.get('size_unit_id', '')
                            product_type_name = ProductTypes.objects.get(id=product_type).name if product_type else ''
                            variant_name = ProductVariants.objects.get(id=variant).name if variant else ''
                            size_label = Sizes.objects.get(id=size).size_label if size else ''
                            size_unit_name = SizeUnits.objects.get(id=size_unit).unit_name if size_unit else ''
                            
                            return f"Deleted ({product_type_name} - {variant_name} ({size_label} {size_unit_name}))"
                        except:
                            pass
                    
                    return f"Deleted ({self.entity_type.replace('_', ' ').title()})"
                return "Deleted Entity"
            
            return f"Entity #{self.entity_id}"

    def get_details_display(self):
        """Pretty-print before/after changes with human-readable names and clean formatting."""
        try:
            if not self.details:
                return ""

            def humanize_field(key, value):
                """Convert FK ids or choice fields into readable names."""
                if value is None:
                    return None

                if key == "reason":
                    return dict(Withdrawals.REASON_CHOICES).get(value, value)
                if key == "sales_channel":
                    return dict(Withdrawals.SALES_CHANNEL_CHOICES).get(value, value)
                if key == "price_type":
                    return dict(Withdrawals.PRICE_TYPE_CHOICES).get(value, value)
                if key == "item_type":
                    return dict(Withdrawals.ITEM_TYPE_CHOICES).get(value, value)
                if key == "category" and isinstance(value, str):
                    return value.replace('_', ' ').title()
                if key == "product_id":
                    try:
                        product = Products.objects.select_related("product_type", "variant", "size_unit", "size").get(id=value)
                        return str(product)
                    except Products.DoesNotExist:
                        return f"Product #{value}"

                if key == "variant_id":
                    try:
                        return ProductVariants.objects.get(id=value).name
                    except ProductVariants.DoesNotExist:
                        return f"Variant #{value}"

                if key == "product_type_id":
                    try:
                        return ProductTypes.objects.get(id=value).name
                    except ProductTypes.DoesNotExist:
                        return f"ProductType #{value}"

                if key == "size_id":
                    try:
                        return Sizes.objects.get(id=value).size_label
                    except Sizes.DoesNotExist:
                        return f"Size #{value}"

                if key in ("size_unit_id", "unit_id"):
                    try:
                        return SizeUnits.objects.get(id=value).unit_name
                    except SizeUnits.DoesNotExist:
                        return f"Unit #{value}"

                if key == "material_id":
                    try:
                        return RawMaterials.objects.get(id=value).name
                    except RawMaterials.DoesNotExist:
                        return f"Material #{value}"

                if key == "srp_price_id":
                    try:
                        return str(SrpPrices.objects.get(id=value))
                    except SrpPrices.DoesNotExist:
                        return f"SRP #{value}"

                if key == "unit_price_id":
                    try:
                        return str(UnitPrices.objects.get(id=value))
                    except UnitPrices.DoesNotExist:
                        return f"Unit Price #{value}"

                return value

            ignore_fields = [
                "id",
                "created_by_admin_id",
                "date_created",
                "expiration_date",
                "manufactured_date",
                "batch_date",
                "received_date",
                "description",
                "date",
                "withdrawal_id", 
                "item_id", 
                "item_type",
            ]

            if self.entity_type == "user":
                ignore_fields.append("date_joined")

            def format_key(key):
                return key.replace("_id", "").replace("_", " ").title()

            if "before" in self.details and "after" in self.details:
                diffs = []
                before, after = self.details["before"], self.details["after"]
                for key in after.keys():
                    if key in ignore_fields:
                        continue
                    b, a = humanize_field(key, before.get(key)), humanize_field(key, after.get(key))
                    if b != a:
                        # Special handling for is_archived field
                        if key == "is_archived":
                            if a == True or a == "True":
                                diffs.append("Archived")
                            elif a == False or a == "False":
                                diffs.append("Restored")
                        else:
                            diffs.append(f"{format_key(key)}: {b} → {a}")

                return " | ".join(diffs) if diffs else "None"

            elif "after" in self.details:
                after = self.details["after"]
                summary = ", ".join(
                    f"{format_key(k)}: {humanize_field(k, v)}"
                    for k, v in after.items() 
                    if k not in ignore_fields 
                    and v is not None 
                    and not (k == "is_archived" and v is False)
                )
                return summary

            elif "before" in self.details:
                before = self.details["before"]
                summary = ", ".join(
                    f"{format_key(k)}: {humanize_field(k, v)}"
                    for k, v in before.items() 
                    if k not in ignore_fields 
                    and v is not None 
                    and not (k == "is_archived" and v is False)
                )
                return summary

            return json.dumps(self.details)

        except Exception:
            return str(self.details)


class HistoryLogTypes(models.Model):
    id = models.BigAutoField(primary_key=True)
    category = models.CharField(max_length=100)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'history_log_types'

    def __str__(self):
        return self.category


class Notifications(models.Model):
    id = models.BigAutoField(primary_key=True)
    item_type = models.CharField(max_length=12)
    item_id = models.BigIntegerField()
    notification_type = models.CharField(max_length=20)
    notification_timestamp = models.DateTimeField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'notifications'

    @property
    def css_class(self):
        mapping = {
            "EXPIRATION_ALERT": "notif-warning",
            "EXPIRED_TODAY": "notif-danger",
            "EXPIRES_IN_WEEK": "notif-warning",
            "EXPIRES_IN_MONTH": "notif-info",
            "LOW_STOCK": "notif-info",
            "OUT_OF_STOCK": "notif-danger",
            "STOCK_HEALTHY": "notif-info",
        }
        return mapping.get(self.notification_type.upper(), "notif-info")

    @property
    def icon_class(self):
        mapping = {
            "EXPIRATION_ALERT": "la la-hourglass-half",
            "EXPIRED_TODAY": "la la-times-circle",
            "EXPIRES_IN_WEEK": "la la-exclamation-triangle",
            "EXPIRES_IN_MONTH": "la la-hourglass-half",
            "LOW_STOCK": "la la-arrow-down",
            "OUT_OF_STOCK": "la la-exclamation-circle",
            "STOCK_HEALTHY": "la la-check-circle",
        }
        return mapping.get(self.notification_type.upper(), "la la-bell")

    @property
    def formatted_message(self):
        notif_type = self.notification_type.upper()
        from realsproj.models import ProductBatches, RawMaterialBatches, Products, RawMaterials
        item_name = "Unknown Item"

        try:
            if self.item_type.upper() == "PRODUCT":
        
                if notif_type in ["EXPIRATION_ALERT", "EXPIRED_TODAY", "EXPIRES_IN_WEEK", "EXPIRES_IN_MONTH"]:
                    batch = (
                        ProductBatches.objects.filter(id=self.item_id)
                        .select_related(
                            "product__product_type",
                            "product__variant",
                            "product__size_unit",
                            "product__size"
                        ).first()
                    )
                    if batch and batch.product:
                        p = batch.product
                        product_type = getattr(p.product_type, "name", "")
                        variant = getattr(p.variant, "name", "")
                        size_label = getattr(p.size, "size_label", None)
                        size_unit = getattr(p.size_unit, "unit_name", None)
                        size_text = f" ({size_label} {size_unit})" if size_label and size_unit else f" ({size_unit})" if size_unit else ""
                        batch_date = batch.batch_date.strftime("%m/%d/%Y") if batch.batch_date else "Unknown"
                        item_name = f"{product_type} - {variant}{size_text} Batch {batch_date}"
                else:
                    product = (
                        Products.objects.filter(id=self.item_id)
                        .select_related(
                            "product_type",
                            "variant",
                            "size_unit",
                            "size"
                        ).first()
                    )
                    if product:
                        product_type = getattr(product.product_type, "name", "")
                        variant = getattr(product.variant, "name", "")
                        size_label = getattr(product.size, "size_label", None)
                        size_unit = getattr(product.size_unit, "unit_name", None)
                        size_text = f" ({size_label} {size_unit})" if size_label and size_unit else f" ({size_unit})" if size_unit else ""
                        item_name = f"{product_type} - {variant}{size_text}"

            elif self.item_type.upper() == "RAW_MATERIAL":
                if notif_type in ["EXPIRATION_ALERT", "EXPIRED_TODAY", "EXPIRES_IN_WEEK", "EXPIRES_IN_MONTH"]:
                    batch = (
                        RawMaterialBatches.objects.filter(id=self.item_id)
                        .select_related("material__unit")
                        .first()
                    )
                    if batch and batch.material:
                        material_name = getattr(batch.material, "name", "")
                        unit_name = getattr(batch.material.unit, "unit_name", "")
                        batch_date = batch.batch_date.strftime("%m/%d/%Y") if batch.batch_date else "Unknown"
                        item_name = f"{material_name} ({unit_name}) Batch {batch_date}"
                else:

                    material = (
                        RawMaterials.objects.filter(id=self.item_id)
                        .select_related("unit")
                        .first()
                    )
                    if material:
                        material_name = getattr(material, "name", "")
                        unit_name = getattr(material.unit, "unit_name", "")
                        item_name = f"{material_name} ({unit_name})"

        except Exception as e:
            print(f"[Notification Error] Failed to format {self.item_type} #{self.item_id}: {e}")
            item_name = f"Unknown ({self.item_type} #{self.item_id})"

        if notif_type in ["EXPIRATION_ALERT", "EXPIRED_TODAY", "EXPIRES_IN_WEEK", "EXPIRES_IN_MONTH"]:
            return f"{item_name} {self._expiration_message()}"
        elif notif_type == "LOW_STOCK":
            return f"LOW STOCK: {item_name}"
        elif notif_type == "OUT_OF_STOCK":
            return f"OUT OF STOCK: {item_name}"
        elif notif_type == "STOCK_HEALTHY":
            return f"Stock back to healthy: {item_name}"
        else:
            return f"{notif_type}: {item_name}"

    def _expiration_message(self):
        today = timezone.localdate()

        try:
            if self.item_type.upper() == "PRODUCT":
                from .models import ProductBatches
                batch = ProductBatches.objects.filter(id=self.item_id).first()
            else:
                from .models import RawMaterialBatches
                batch = RawMaterialBatches.objects.filter(id=self.item_id).first()

            if not batch or not batch.expiration_date:
                return "has no expiration date"

            delta_days = (batch.expiration_date - today).days
            if delta_days > 30:
                return f"will expire in more than a month ({batch.expiration_date})"
            elif 7 < delta_days <= 30:
                return f"will expire in a month ({batch.expiration_date})"
            elif 1 <= delta_days <= 7:
                return f"will expire in a week ({batch.expiration_date})"
            elif delta_days == 0:
                return "expires today"
            else:
                return f"has expired ({batch.expiration_date})"

        except Exception as e:
            print(f"[Expiration Error] {self.item_type} #{self.item_id}: {e}")
            return "has unknown expiration date"


class ProductBatches(models.Model):
    id = models.BigAutoField(primary_key=True)
    batch_date = models.DateField(default=timezone.localdate)
    product = models.ForeignKey('Products', models.DO_NOTHING)
    quantity = models.IntegerField()
    manufactured_date = models.DateField(default=timezone.localdate)
    created_by_admin = models.ForeignKey('AuthUser', models.DO_NOTHING)
    deduct_raw_material = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    is_expired = models.BooleanField(blank=True, null=True)

    expiration_date = models.GeneratedField( 
        expression="manufactured_date + interval '1 year'",
        output_field=models.DateField(),
        db_persist=True,
    )

    class Meta:
        managed = False
        db_table = 'product_batches'

    def __str__(self):
        local_date = timezone.localtime(self.date)


class ProductInventory(models.Model):
    product = models.OneToOneField('Products', models.DO_NOTHING, primary_key=True)
    total_stock = models.DecimalField(max_digits=10, decimal_places=2)
    restock_threshold = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'product_inventory'


class ProductRecipes(models.Model):
    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(
        "Products",
        on_delete=models.CASCADE,
        related_name="recipes"  # lets you do product.recipes.all()
    )
    material = models.ForeignKey(
        "RawMaterials",
        on_delete=models.DO_NOTHING,
        db_column="material_id"
    )
    quantity_needed = models.DecimalField(max_digits=10, decimal_places=2)
    created_by_admin = models.ForeignKey("AuthUser", models.DO_NOTHING)
    yield_factor = models.DecimalField(max_digits=5, decimal_places=2, default=1.00)

    class Meta:
        db_table = "product_recipes" 


class ProductTypes(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'product_types'

    def __str__(self):
        return self.name


class ProductVariants(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'product_variants'

    def __str__(self):
        return self.name


class Products(models.Model):
    id = models.BigAutoField(primary_key=True)
    product_type = models.ForeignKey(ProductTypes, models.DO_NOTHING)
    variant = models.ForeignKey(ProductVariants, models.DO_NOTHING)
    size_unit = models.ForeignKey('SizeUnits', models.DO_NOTHING)
    unit_price = models.ForeignKey('UnitPrices', models.DO_NOTHING)
    srp_price = models.ForeignKey('SrpPrices', models.DO_NOTHING)
    description = models.TextField(blank=True, null=True)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)
    date_created = models.DateTimeField(default=timezone.now)
    size = models.ForeignKey('Sizes', models.DO_NOTHING, blank=True, null=True)
    photo = models.ImageField(upload_to="product_photos/", blank=True, null=True)
    is_archived = models.BooleanField(default=False)
    barcode = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'products'

    def __str__(self):
        return f"{self.product_type.name} - {self.variant.name} ({self.size} {self.size_unit.unit_name})"


class RawMaterialBatches(models.Model):
    id = models.BigAutoField(primary_key=True)
    material = models.ForeignKey('RawMaterials', models.DO_NOTHING)
    batch_date = models.DateField(default=timezone.localdate)
    received_date = models.DateField(default=timezone.localdate)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    expiration_date = models.DateField(blank=True, null=True)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)
    is_archived = models.BooleanField(default=False)
    is_expired = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'raw_material_batches'


class RawMaterialInventory(models.Model):
    material = models.OneToOneField('RawMaterials', models.DO_NOTHING, primary_key=True)
    total_stock = models.DecimalField(max_digits=10, decimal_places=2)
    reorder_threshold = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'raw_material_inventory'


class RawMaterials(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=45)
    unit = models.ForeignKey('SizeUnits', models.DO_NOTHING)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)
    size = models.DecimalField(max_digits=10, decimal_places=2)
    date_created = models.DateTimeField(default=timezone.now)
    is_archived = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'raw_materials'

    def __str__(self):
        return f"{self.name} ({self.unit}) - ₱{self.price_per_unit}"


class Sales(models.Model):
    id = models.BigAutoField(primary_key=True)
    category = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    description = models.TextField(blank=True, null=True)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)
    is_archived = models.BooleanField(default=False) # <-- Idagdag ito

    class Meta:
        managed = False
        db_table = 'sales'

    def __str__(self):
        return f"{self.category} - ₱{self.amount} on {self.date.strftime('%Y-%m-%d')}"


class SalesSummary(models.Model):
    id = models.BigIntegerField(primary_key=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'sales_summary'


class SizeUnits(models.Model):
    id = models.BigAutoField(primary_key=True)
    unit_name = models.CharField(max_length=45)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'size_units'

    def __str__(self):
        return self.unit_name


class Sizes(models.Model):
    id = models.BigAutoField(primary_key=True)
    size_label = models.CharField(max_length=255)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'sizes'

    def __str__(self):
        return self.size_label


class SrpPrices(models.Model):
    id = models.BigAutoField(primary_key=True)
    srp_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'srp_prices'

    def __str__(self):
        return f"₱{self.srp_price}"


class StockChanges(models.Model):
    id = models.BigAutoField(primary_key=True)
    item_type = models.CharField(max_length=12)
    item_id = models.BigIntegerField()
    quantity_change = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.TextField()
    date = models.DateTimeField()
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)
    is_archived = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'stock_changes'

    def get_item(self):
        if not self.item_type:
            return None

        item_type = self.item_type.strip().lower()

        if item_type in ("raw", "raw_material", "rawmaterials"):
            return RawMaterials.objects.filter(id=self.item_id).first()
        elif item_type in ("product", "products"):
            return Products.objects.filter(id=self.item_id).first()
        return None

    @property
    def item_display(self):
        """Human-readable item representation."""
        item = self.get_item()
        if item:
            return str(item)
        return f"[{self.item_type}] Unknown Item (ID: {self.item_id})"

    def __str__(self):
        return self.item_display


class UnitPrices(models.Model):
    id = models.BigAutoField(primary_key=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'unit_prices'

    def __str__(self):
        return f"₱{self.unit_price}"

class Discounts(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('PERCENT', 'Percentage'),
        ('AMOUNT', 'Fixed Amount'),
    ]

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=50)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    created_by_admin = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "discounts"

    def __str__(self):
        if self.discount_type == "PERCENT":
            return f"{self.name} ({self.value}%)"
        return f"{self.name} (-{self.value})"
    

class UserActivity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_logout = models.DateTimeField(blank=True, null=True)
    active = models.BooleanField(default=False)
    last_activity = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "user_activity"

    def __str__(self):
        return f"{self.user.username} Activity"
    
    @property
    def is_truly_active(self):
        """
        User is truly active if:
        - They are marked as active (logged in)
        - AND their last activity was within the last 5 minutes
        """
        if not self.active:
            return False
        
        if not self.last_activity:
            return False

        time_threshold = timezone.now() - timedelta(minutes=5)
        return self.last_activity >= time_threshold
    

class Withdrawals(models.Model):
    id = models.BigAutoField(primary_key=True)

    ITEM_TYPE_CHOICES = [
        ('PRODUCT', 'Product'),
        ('RAW_MATERIAL', 'Raw Material'),
    ]
    item_type = models.CharField(max_length=12, choices=ITEM_TYPE_CHOICES)
    item_id = models.BigIntegerField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2)

    REASON_CHOICES = [
        ('SOLD', 'Sold'),
        ('EXPIRED', 'Expired'),
        ('DAMAGED', 'Damaged'),
        ('RETURNED', 'Returned'),
        ('OTHERS', 'Others'),
    ]
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)

    date = models.DateTimeField(auto_now_add=True)
    created_by_admin = models.ForeignKey(
        User,
        on_delete=models.DO_NOTHING,
        db_column="created_by_admin_id"
    )

    SALES_CHANNEL_CHOICES = [
        ('ORDER', 'Order'),
        ('CONSIGNMENT', 'Consignment'),
        ('RESELLER', 'Reseller'),
        ('PHYSICAL_STORE', 'Physical Store'),
    ]
    sales_channel = models.CharField(
        max_length=20,
        choices=SALES_CHANNEL_CHOICES,
        null=True,
        blank=True
    )

    PRICE_TYPE_CHOICES = [
        ('UNIT', 'Unit Price'),
        ('SRP', 'SRP'),
    ]
    price_type = models.CharField(
        max_length=10,
        choices=PRICE_TYPE_CHOICES,
        null=True,
        blank=True
    )

    # NEW DISCOUNT FIELDS
    discount = models.ForeignKey(
        Discounts,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    custom_discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    custom_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_archived = models.BooleanField(default=False)
    
    # NEW CUSTOMER AND PAYMENT FIELDS
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    
    PAYMENT_STATUS_CHOICES = [
        ('PAID', 'Paid'),
        ('UNPAID', 'Unpaid'),
        ('PARTIAL', 'Partial Payment'),
    ]
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='PAID',
        null=True,
        blank=True
    )
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    order_group_id = models.BigIntegerField(null=True, blank=True)
    
    actual_unit_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Base price (unit or SRP) at time of sale"
    )
    actual_discount_percent = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Discount percentage applied"
    )
    actual_discount_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Discount amount applied"
    )
    final_price_per_unit = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Final price per unit after discount"
    )
    total_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Total amount (quantity × final_price_per_unit)"
    )

    class Meta:
        managed = False  # existing table
        db_table = 'withdrawals'

    def __str__(self):
        return f"{self.item_type} {self.item_id} - {self.quantity}"

    def get_item_display(self):
        if self.item_type == "PRODUCT":
            from .models import Products
            try:
                product = Products.objects.get(id=self.item_id)
                return str(product)
            except Products.DoesNotExist:
                return f"Unknown Product (ID {self.item_id})"
        elif self.item_type == "RAW_MATERIAL":
            from .models import RawMaterials
            try:
                material = RawMaterials.objects.get(id=self.item_id)
                return str(material)
            except RawMaterials.DoesNotExist:
                return f"Unknown Material (ID {self.item_id})"
        return f"Unknown Item (ID {self.item_id})"

    def compute_revenue(self):
        """
        Compute revenue using stored actual prices.
        Falls back to current prices for old records (before fix).
        """
        if self.item_type == "PRODUCT" and self.reason == "SOLD":
        
            if self.total_amount is not None:
                return self.total_amount

            from .models import Products
            try:
                product = Products.objects.get(id=self.item_id)
                base_revenue = Decimal(self.quantity) * product.srp_price.srp_price

                discount_value = Decimal(0)
                if self.discount:
                    if self.discount.discount_type == 'PERCENT':
                        discount_value = base_revenue * (self.discount.value / 100)
                    else:
                        discount_value = self.discount.value
                elif self.custom_discount_value:
                    discount_value = self.custom_discount_value

                return base_revenue - discount_value
            except Products.DoesNotExist:
                return Decimal(0)
        return Decimal(0)

    @staticmethod
    def get_queryset(request):
        query = request.GET.get("q")
        qs = Withdrawals.objects.all().order_by("-date")
        if query:
            qs = qs.filter(
                Q(reason__icontains=query) |
                Q(item_type__icontains=query)
            )
        return qs


class User2FASettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='twofa_settings')
    is_enabled = models.BooleanField(default=False)
    method = models.CharField(max_length=10, choices=[('email', 'Email'), ('sms', 'SMS')], default='email')
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    backup_email = models.EmailField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False  
        db_table = 'user_2fa_settings'


class UserOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_codes')
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'user_otp'


class TrustedDevice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_devices')
    device_fingerprint = models.CharField(max_length=255)
    device_name = models.CharField(max_length=255)
    browser = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField()
    last_used = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False 
        db_table = 'trusted_devices'
        unique_together = ['user', 'device_fingerprint']


class LoginAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_attempts', null=True, blank=True)
    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField()
    device_fingerprint = models.CharField(max_length=255, blank=True)
    browser = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=255, blank=True)
    success = models.BooleanField(default=False)
    required_otp = models.BooleanField(default=False)
    is_trusted_device = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False 
        db_table = 'login_attempts'


class PriceHistory(models.Model):
    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name='price_changes')
    
    PRICE_TYPE_CHOICES = [
        ('UNIT', 'Unit Price'),
        ('SRP', 'SRP'),
    ]
    price_type = models.CharField(max_length=10, choices=PRICE_TYPE_CHOICES)
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    changed_by_admin = models.ForeignKey(AuthUser, on_delete=models.SET_NULL, null=True, db_column='changed_by_admin_id')
    changed_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, null=True)
    
    class Meta:
        managed = False
        db_table = 'price_history'
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.product} - {self.price_type}: ₱{self.old_price} → ₱{self.new_price}"
    
    @property
    def price_change_percent(self):
        """Calculate percentage change in price"""
        if self.old_price and self.old_price > 0:
            change = ((self.new_price - self.old_price) / self.old_price) * 100
            return round(change, 2)
        return None
    
    @property
    def price_change_amount(self):
        """Calculate absolute change in price"""
        if self.old_price:
            return self.new_price - self.old_price
        return None