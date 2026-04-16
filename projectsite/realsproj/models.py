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
                    if self.details:
                        # Try different data structures based on log type
                        data = None
                        if 'before' in self.details:
                            data = self.details['before']
                        elif 'deleted' in self.details:
                            data = self.details['deleted']
                        elif 'created' in self.details:
                            data = self.details['created']
                        
                        if data:
                            reason = dict(Withdrawals.REASON_CHOICES).get(data.get('reason'), data.get('reason', 'Unknown'))
                            item_type = dict(Withdrawals.ITEM_TYPE_CHOICES).get(data.get('item_type'), data.get('item_type', 'Unknown'))
                            quantity = data.get('quantity', 'Unknown')
                            sales_channel = dict(Withdrawals.SALES_CHANNEL_CHOICES).get(data.get('sales_channel'), data.get('sales_channel', 'N/A'))
                            
                            # Get product/material name if available
                            item_name = "Unknown Item"
                            if data.get('item_type') == 'PRODUCT' and data.get('item_id'):
                                try:
                                    product = Products.objects.select_related(
                                        'product_type', 'variant', 'size', 'size_unit'
                                    ).get(id=data.get('item_id'))
                                    item_name = f"{product.product_type.name} - {product.variant.name}"
                                    if product.size:
                                        item_name += f" ({product.size.size_label} {product.size_unit.unit_name})"
                                except Products.DoesNotExist:
                                    pass
                            elif data.get('item_type') == 'RAW_MATERIAL' and data.get('item_id'):
                                try:
                                    material = RawMaterials.objects.get(id=data.get('item_id'))
                                    item_name = material.name
                                except RawMaterials.DoesNotExist:
                                    pass
                            
                            # Format like: "Deleted (Sold - 2.0 Yema - Mani (120 Grams) (ORDER))"
                            return f"Deleted ({reason} - {quantity} {item_name} ({sales_channel}))"
                    
                    return f"Deleted Withdrawal #{self.entity_id}"

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

            elif self.entity_type == "stock_change":
                try:
                    sc = StockChanges.objects.get(pk=self.entity_id)
                    item = sc.get_item()
                    if item:
                        quantity_sign = "+" if sc.quantity_change >= 0 else ""
                        return f"{str(item)} Quantity Change: {quantity_sign}{sc.quantity_change}"
                    else:
                        quantity_sign = "+" if sc.quantity_change >= 0 else ""
                        return f"[{sc.item_type}] Unknown Item (ID: {sc.item_id}) Quantity Change: {quantity_sign}{sc.quantity_change}"
                except StockChanges.DoesNotExist:
                    return f"Deleted Stock Change #{self.entity_id}"

            else:
                return f"Entity #{self.entity_id}"

        except Exception:
            # Entity doesn't exist in database - try to get info from details
            # Check both 'before' (for updates/deletes) and 'after' (for creates) fields
            entity_data = None
            if self.details:
                if 'before' in self.details:
                    entity_data = self.details['before']
                elif 'after' in self.details:
                    entity_data = self.details['after']
            
            if entity_data:
                if self.entity_type == "product":
                    try:
                        product_type = entity_data.get('product_type_id', '')
                        variant = entity_data.get('variant_id', '')
                        size = entity_data.get('size_id', '')
                        size_unit = entity_data.get('size_unit_id', '')
                        product_type_name = ProductTypes.objects.get(id=product_type).name if product_type else ''
                        variant_name = ProductVariants.objects.get(id=variant).name if variant else ''
                        size_label = Sizes.objects.get(id=size).size_label if size else ''
                        size_unit_name = SizeUnits.objects.get(id=size_unit).unit_name if size_unit else ''
                        
                        return f"Deleted ({product_type_name} - {variant_name} ({size_label} {size_unit_name}))"
                    except:
                        pass
                
                elif self.entity_type == "raw_material":
                    try:
                        name = entity_data.get('name', '')
                        unit_id = entity_data.get('unit_id', '')
                        price = entity_data.get('price_per_unit', '')
                        
                        # Safely get unit name
                        unit_name = ''
                        if unit_id:
                            try:
                                unit_name = SizeUnits.objects.get(id=unit_id).unit_name
                            except SizeUnits.DoesNotExist:
                                unit_name = 'Unknown Unit'
                        
                        return f"Deleted ({name} ({unit_name}) - ₱{price})"
                    except:
                        pass
                
                elif self.entity_type == "product_batch":
                    try:
                        product_id = entity_data.get('product_id', '')
                        if product_id:
                            p = Products.objects.select_related(
                                "product_type", "variant", "size_unit", "size"
                            ).get(pk=product_id)
                            return f"Deleted ({p.product_type.name} - {p.variant.name} ({p.size.size_label if p.size else ''} {p.size_unit.unit_name}))"
                    except:
                        pass
                
                elif self.entity_type == "raw_material_batch":
                    try:
                        material_id = entity_data.get('material_id', '')
                        if material_id:
                            rm = RawMaterials.objects.get(pk=material_id)
                            return f"Deleted ({rm.name})"
                    except:
                        pass
                
                elif self.entity_type == "expense":
                    try:
                        category = entity_data.get('category', '')
                        if category:
                            return f"{category}"
                        return "Deleted (Expense)"
                    except:
                        pass
                
                elif self.entity_type == "sale":
                    try:
                        category = entity_data.get('category', '')
                        if category:
                            formatted_category = category.replace('_', ' ').title()
                            return f"{formatted_category}"
                        return "Deleted (Sale)"
                    except:
                        pass
                
                elif self.entity_type == "product_type":
                    try:
                        name = entity_data.get('name', '')
                        return f"Deleted ({name})"
                    except:
                        pass
                
                elif self.entity_type == "product_variant":
                    try:
                        name = entity_data.get('name', '')
                        return f"Deleted ({name})"
                    except:
                        pass
                
                elif self.entity_type == "size":
                    try:
                        size_label = entity_data.get('size_label', '')
                        return f"Deleted ({size_label})"
                    except:
                        pass
                
                elif self.entity_type == "size_unit":
                    try:
                        unit_name = entity_data.get('unit_name', '')
                        return f"Deleted (Size Unit: {unit_name})"
                    except:
                        pass
                
                elif self.entity_type == "unit_price":
                    try:
                        unit_price = entity_data.get('unit_price', '')
                        return f"Deleted (Unit Price: ₱{unit_price})"
                    except:
                        pass
                
                elif self.entity_type == "srp_price":
                    try:
                        srp_price = entity_data.get('srp_price', '')
                        return f"Deleted (SRP Price: ₱{srp_price})"
                    except:
                        pass
                
                elif self.entity_type == "stock_change":
                    try:
                        item_type = entity_data.get('item_type', '')
                        item_id = entity_data.get('item_id', '')
                        quantity_change = entity_data.get('quantity_change', '')
                        quantity_sign = "+" if str(quantity_change).replace('-', '').replace('+', '').replace('.', '').isdigit() and float(quantity_change) >= 0 else ""
                        
                        item_name = f"[{item_type}] Item #{item_id}"
                        if item_type and item_id:
                            try:
                                if item_type.lower() in ("product", "products"):
                                    p = Products.objects.select_related("product_type", "variant", "size_unit", "size").get(pk=item_id)
                                    item_name = f"{p.product_type.name} - {p.variant.name} ({p.size.size_label if p.size else ''} {p.size_unit.unit_name})"
                                elif item_type.lower() in ("raw", "raw_material", "rawmaterials"):
                                    rm = RawMaterials.objects.select_related("unit").get(pk=item_id)
                                    item_name = f"{rm.name} ({rm.unit.unit_name}) - ₱{rm.price_per_unit}"
                            except:
                                pass
                        
                        return f"Deleted ({item_name} Quantity Change: {quantity_sign}{quantity_change})"
                    except:
                        pass
                
                # Generic fallback for any entity type with details
                return f"Deleted ({self.entity_type.replace('_', ' ').title()})"
            
            return f"Entity #{self.entity_id}"
    
    def get_admin_display(self):
        """Safely get admin username even if user is deleted or deactivated."""
        try:
            if self.admin:
                # Check if user is deleted (username starts with 'deleted_user_')
                if self.admin.username.startswith('deleted_user_'):
                    # Try to extract original username from first_name field
                    if self.admin.first_name and self.admin.first_name.startswith('ORIGINAL_USERNAME:'):
                        parts = self.admin.first_name.split('|')
                        original_username = parts[0].replace('ORIGINAL_USERNAME:', '')
                        return f"{original_username} (Deleted User)"
                    # Fallback: try to extract from username pattern deleted_user_X_timestamp
                    parts = self.admin.username.split('_')
                    if len(parts) >= 3 and parts[0] == 'deleted' and parts[1] == 'user':
                        try:
                            # Extract the original username part (usually the third part)
                            original_username = parts[2]
                            return f"{original_username} (Deleted User)"
                        except:
                            pass
                    return "Deleted User"
                # Check if user is deactivated (username starts with 'inactive_user_')
                elif self.admin.username.startswith('inactive_user_'):
                    # Try to extract original username from first_name field
                    if self.admin.first_name and self.admin.first_name.startswith('ORIGINAL_USERNAME:'):
                        parts = self.admin.first_name.split('|')
                        original_username = parts[0].replace('ORIGINAL_USERNAME:', '')
                        return f"{original_username} (Deactivated)"
                    return "Deactivated User"
                return self.admin.username
        except Exception:
            # If admin is deleted, try to get from details
            if self.details and 'admin_username' in self.details:
                return f"{self.details['admin_username']} (Deleted)"
            return "Unknown User"
        return "Unknown User"

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
                if key == "payment_status":
                    return dict(Withdrawals.PAYMENT_STATUS_CHOICES).get(value, value)
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

            # Handle withdrawal-specific data structures first
            if self.entity_type == "withdrawal":
                if "created" in self.details:
                    # Withdrawal Created (new format with nested data)
                    data = self.details["created"]
                    parts = []
                    if data.get('reason'):
                        parts.append(f"Reason: {humanize_field('reason', data['reason'])}")
                    if data.get('quantity'):
                        parts.append(f"Quantity: {data['quantity']}")
                    if data.get('sales_channel'):
                        parts.append(f"Channel: {humanize_field('sales_channel', data['sales_channel'])}")
                    if data.get('payment_status'):
                        parts.append(f"Status: {humanize_field('payment_status', data['payment_status'])}")
                    if data.get('customer_name'):
                        parts.append(f"Customer: {data['customer_name']}")
                    return " | ".join(parts)
                
                elif "updated" in self.details:
                    # Withdrawal Updated (new format with nested before/after)
                    update_data = self.details["updated"]
                    before = update_data.get("before", {})
                    after = update_data.get("after", {})
                    
                    changes = []
                    for key in ['quantity', 'reason', 'payment_status', 'sales_channel', 'customer_name']:
                        old_val = before.get(key)
                        new_val = after.get(key)
                        if old_val != new_val:
                            old_display = humanize_field(key, old_val) if old_val else "None"
                            new_display = humanize_field(key, new_val) if new_val else "None"
                            changes.append(f"{format_key(key)}: {old_display} → {new_display}")
                    
                    return " | ".join(changes) if changes else "Updated"
                
                elif "deleted" in self.details:
                    # Withdrawal Deleted (new format with nested data)
                    data = self.details["deleted"]
                    parts = []
                    if data.get('reason'):
                        parts.append(f"Reason: {humanize_field('reason', data['reason'])}")
                    if data.get('quantity'):
                        parts.append(f"Quantity: {data['quantity']}")
                    if data.get('sales_channel'):
                        parts.append(f"Channel: {humanize_field('sales_channel', data['sales_channel'])}")
                    if data.get('payment_status'):
                        parts.append(f"Status: {humanize_field('payment_status', data['payment_status'])}")
                    if data.get('customer_name'):
                        parts.append(f"Customer: {data['customer_name']}")
                    return " | ".join(parts)
                
                elif "archived" in self.details:
                    # Withdrawal Archived/Restored (new format)
                    archive_data = self.details["archived"]
                    before = archive_data.get("before", {})
                    after = archive_data.get("after", {})
                    
                    if after.get("is_archived") == True:
                        return "Archived"
                    elif after.get("is_archived") == False:
                        return "Restored"
                    else:
                        return "Archive Status Changed"

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
            "PRE_LOW_STOCK": "notif-warning",
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
            "PRE_LOW_STOCK": "la la-exclamation-triangle",
            "OUT_OF_STOCK": "la la-exclamation-circle",
            "STOCK_HEALTHY": "la la-check-circle",
        }
        return mapping.get(self.notification_type.upper(), "la la-bell")

    @property
    def formatted_message(self):
        notif_type = self.notification_type.upper()
        item_name = "Unknown Item"
        expiring_qty = None

        try:
            if self.item_type.upper() == "PRODUCT":
                if notif_type == "PRE_LOW_STOCK":
                    product = Products.objects.filter(id=self.item_id).select_related(
                        "product_type",
                        "variant",
                        "size_unit",
                        "size"
                    ).first()

                    if product:
                        p = product
                        product_type = getattr(p.product_type, "name", "")
                        variant = getattr(p.variant, "name", "")
                        size_label = getattr(p.size, "size_label", None)
                        size_unit = getattr(p.size_unit, "unit_name", None)
                        size_text = f" ({size_label} {size_unit})" if size_label and size_unit else f" ({size_unit})" if size_unit else ""

                        next_batch = ProductBatches.objects.filter(
                            product_id=p.id,
                            is_archived=False
                        ).exclude(is_expired=True).order_by("batch_date").first()
                        batch_date = None
                        if next_batch:
                            batch_date = next_batch.batch_date.strftime("%m/%d/%Y") if next_batch.batch_date else "Unknown"

                        base_name = f"{product_type} - {variant}{size_text}"
                        item_name = f"{base_name} Batch {batch_date}" if batch_date else base_name

                        expiring_qty = ProductBatches.objects.filter(
                            product_id=p.id,
                            is_archived=False,
                            is_expired=False,
                            expiration_date__isnull=False,
                            expiration_date__lte=timezone.localdate() + timezone.timedelta(days=7)
                        ).aggregate(total=models.Sum('quantity'))['total'] or 0
                    else:
                        batch = ProductBatches.objects.filter(id=self.item_id).select_related(
                            "product__product_type",
                            "product__variant",
                            "product__size_unit",
                            "product__size"
                        ).first()
                        if batch and batch.product:
                            p = batch.product
                            product_type = getattr(p.product_type, "name", "")
                            variant = getattr(p.variant, "name", "")
                            size_label = getattr(p.size, "size_label", None)
                            size_unit = getattr(p.size_unit, "unit_name", None)
                            size_text = f" ({size_label} {size_unit})" if size_label and size_unit else f" ({size_unit})" if size_unit else ""
                            batch_date = batch.batch_date.strftime("%m/%d/%Y") if batch.batch_date else "Unknown"
                            item_name = f"{product_type} - {variant}{size_text} Batch {batch_date}"

                            expiring_qty = ProductBatches.objects.filter(
                                product_id=p.id,
                                is_archived=False,
                                is_expired=False,
                                expiration_date__lte=timezone.localdate() + timezone.timedelta(days=7)
                            ).aggregate(total=models.Sum('quantity'))['total'] or 0

                elif notif_type in ["EXPIRATION_ALERT", "EXPIRED_TODAY", "EXPIRES_IN_WEEK", "EXPIRES_IN_MONTH"]:
                    batch = ProductBatches.objects.filter(id=self.item_id).select_related(
                        "product__product_type",
                        "product__variant",
                        "product__size_unit",
                        "product__size"
                    ).first()
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
                    product = Products.objects.filter(id=self.item_id).select_related(
                        "product_type",
                        "variant",
                        "size_unit",
                        "size"
                    ).first()
                    if product:
                        product_type = getattr(product.product_type, "name", "")
                        variant = getattr(product.variant, "name", "")
                        size_label = getattr(product.size, "size_label", None)
                        size_unit = getattr(product.size_unit, "unit_name", None)
                        size_text = f" ({size_label} {size_unit})" if size_label and size_unit else f" ({size_unit})" if size_unit else ""
                        item_name = f"{product_type} - {variant}{size_text}"

            elif self.item_type.upper() == "RAW_MATERIAL":
                if notif_type in ["EXPIRATION_ALERT", "EXPIRED_TODAY", "EXPIRES_IN_WEEK", "EXPIRES_IN_MONTH", "PRE_LOW_STOCK"]:
                    batch = RawMaterialBatches.objects.filter(id=self.item_id).select_related("material__unit").first()
                    if batch and batch.material:
                        material_name = getattr(batch.material, "name", "")
                        unit_name = getattr(batch.material.unit, "unit_name", "")
                        batch_date = batch.batch_date.strftime("%m/%d/%Y") if getattr(batch, "batch_date", None) else "Unknown"
                        item_name = f"{material_name} ({unit_name}) Batch {batch_date}"

                        if notif_type == "PRE_LOW_STOCK":
                            expiring_qty = RawMaterialBatches.objects.filter(
                                material_id=batch.material.id,
                                is_archived=False,
                                is_expired=False,
                                expiration_date__lte=timezone.localdate() + timezone.timedelta(days=7)
                            ).aggregate(total=models.Sum('quantity'))['total'] or 0
                else:
                    material = RawMaterials.objects.filter(id=self.item_id).select_related("unit").first()
                    if material:
                        material_name = getattr(material, "name", "")
                        unit_name = getattr(material.unit, "unit_name", "")
                        item_name = f"{material_name} ({unit_name})"

        except Exception as e:
            print(f"[Notification Error] Failed to format {self.item_type} #{self.item_id}: {e}")
            item_name = f"Unknown ({self.item_type} #{self.item_id})"

        # Build final message
        if notif_type == "PRE_LOW_STOCK" and expiring_qty is not None:
            return f"PRE LOW STOCK: {item_name} – {expiring_qty} items will expire soon, check remaining stock!"
        elif notif_type in ["EXPIRATION_ALERT", "EXPIRED_TODAY", "EXPIRES_IN_WEEK", "EXPIRES_IN_MONTH"]:
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
                batch = ProductBatches.objects.filter(id=self.item_id).first()
            else:
                batch = RawMaterialBatches.objects.filter(id=self.item_id).first()

            if not batch or not getattr(batch, "expiration_date", None):
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
    is_archived = models.BooleanField(default=False)
    is_expired = models.BooleanField(blank=True, null=True)
    expiration_date = models.DateField(blank=True, null=True)
    batch_code = models.CharField(max_length=20, blank=True, null=True)
    packaging = models.ForeignKey('RawMaterials', models.DO_NOTHING, blank=True, null=True)

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

    def get_available_stock(self, days_ahead=7):
        """
        Calculate available stock by subtracting expiring stock from total stock.
        Available Stock = Total Stock - Expiring Soon
        
        Args:
            days_ahead: Number of days to look ahead for expiration (default: 7 days)
        
        Returns:
            Decimal: Available stock quantity
        """
        from django.utils import timezone
        today = timezone.localdate()
        expiration_cutoff = today + timezone.timedelta(days=days_ahead)
        
        # Get batches that are NOT expiring soon (expiration date is more than days_ahead away)
        # Only count batches with quantity > 0
        available_batches = ProductBatches.objects.filter(
            product=self.product,
            is_archived=False,
            expiration_date__gt=expiration_cutoff,
            quantity__gt=0
        ).aggregate(total=models.Sum('quantity'))
        
        available = available_batches['total'] or Decimal(0)
        return Decimal(available)
    
    def get_expiring_stock(self, days_ahead=7):
        """
        Calculate stock expiring within the specified days.
        
        Args:
            days_ahead: Number of days to look ahead for expiration (default: 7 days)
        
        Returns:
            Decimal: Quantity expiring soon
        """
        from django.utils import timezone
        from django.db.models import Q
        today = timezone.localdate()
        expiration_cutoff = today + timezone.timedelta(days=days_ahead)
        
        # Get batches expiring within the timeframe (including today)
        # Must exclude NULL expiration_date values and only include non-archived batches
        # Only count batches that still have quantity > 0 (not fully withdrawn)
        # Exclude batches already marked as is_expired=True (already withdrawn)
        expiring_batches = ProductBatches.objects.filter(
            product=self.product,
            is_archived=False,
            expiration_date__isnull=False,
            expiration_date__lte=expiration_cutoff,
            expiration_date__gte=today,
            quantity__gt=0
        ).exclude(
            is_expired=True
        ).aggregate(total=models.Sum('quantity'))
        
        expiring = expiring_batches['total'] or Decimal(0)
        return Decimal(expiring)
    
    def should_reorder(self, days_ahead=7):
        """
        Determine if reorder is needed based on available stock and threshold.
        
        Returns:
            bool: True if reorder is needed
        """
        available = self.get_available_stock(days_ahead)
        return available < self.restock_threshold
    
    def get_reorder_status(self, days_ahead=7):
        """
        Get detailed reorder status considering expiration dates.
        
        Returns:
            dict: Status information
        """
        available = self.get_available_stock(days_ahead)
        expiring = self.get_expiring_stock(days_ahead)
        
        return {
            'total_stock': self.total_stock,
            'available_stock': available,
            'expiring_stock': expiring,
            'restock_threshold': self.restock_threshold,
            'needs_reorder': available < self.restock_threshold,
            'expiration_impact': self.total_stock - available
        }


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
    product_code = models.CharField(max_length=10)

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
    original_quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
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

    def get_available_stock(self, days_ahead=7):
        """
        Calculate available stock by subtracting expiring stock from total stock.
        Available Stock = Total Stock - Expiring Soon
        
        For packaging materials (which don't expire), returns total_stock directly.
        
        Args:
            days_ahead: Number of days to look ahead for expiration (default: 7 days)
        
        Returns:
            Decimal: Available stock quantity
        """
        from django.utils import timezone
        
        # Check if this is a packaging material (which doesn't expire)
        # Packaging materials have no expiration, so return total_stock directly
        if self.material.category.upper() == 'PACKAGING':
            return Decimal(self.total_stock)
        
        today = timezone.localdate()
        expiration_cutoff = today + timezone.timedelta(days=days_ahead)
        
        # Get batches that are NOT expiring soon (expiration date is more than days_ahead away)
        # Only count batches with quantity > 0
        available_batches = RawMaterialBatches.objects.filter(
            material=self.material,
            is_archived=False,
            expiration_date__gt=expiration_cutoff,
            quantity__gt=0
        ).aggregate(total=models.Sum('quantity'))
        
        available = available_batches['total'] or Decimal(0)
        return Decimal(available)
    
    def get_expiring_stock(self, days_ahead=7):
        """
        Calculate stock expiring within the specified days.
        
        Args:
            days_ahead: Number of days to look ahead for expiration (default: 7 days)
        
        Returns:
            Decimal: Quantity expiring soon
        """
        from django.utils import timezone
        today = timezone.localdate()
        expiration_cutoff = today + timezone.timedelta(days=days_ahead)
        
        # Get batches expiring within the timeframe (including today)
        # Must exclude NULL expiration_date values and only include non-archived batches
        # Only count batches that still have quantity > 0 (not fully withdrawn)
        # Exclude batches already marked as is_expired=True (already withdrawn)
        expiring_batches = RawMaterialBatches.objects.filter(
            material=self.material,
            is_archived=False,
            expiration_date__isnull=False,
            expiration_date__lte=expiration_cutoff,
            expiration_date__gte=today,
            quantity__gt=0
        ).exclude(
            is_expired=True
        ).aggregate(total=models.Sum('quantity'))
        
        expiring = expiring_batches['total'] or Decimal(0)
        return Decimal(expiring)
    
    def should_reorder(self, days_ahead=7):
        """
        Determine if reorder is needed based on available stock and threshold.
        
        Returns:
            bool: True if reorder is needed
        """
        available = self.get_available_stock(days_ahead)
        return available < self.reorder_threshold
    
    def get_reorder_status(self, days_ahead=7):
        """
        Get detailed reorder status considering expiration dates.
        
        Returns:
            dict: Status information
        """
        available = self.get_available_stock(days_ahead)
        expiring = self.get_expiring_stock(days_ahead)
        
        return {
            'total_stock': self.total_stock,
            'available_stock': available,
            'expiring_stock': expiring,
            'reorder_threshold': self.reorder_threshold,
            'needs_reorder': available < self.reorder_threshold,
            'expiration_impact': self.total_stock - available
        }


class RawMaterials(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=45)
    unit = models.ForeignKey('SizeUnits', models.DO_NOTHING)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    created_by_admin = models.ForeignKey(AuthUser, models.DO_NOTHING)
    size = models.CharField(max_length=50)
    date_created = models.DateTimeField(default=timezone.now)
    is_archived = models.BooleanField(default=False)
    category = models.CharField(max_length=30)

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
        ('REPLACEMENT_FOR_RETURNED', 'Replacement for Returned Items'),
        ('OTHERS', 'Others'),
    ]
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)

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
        blank=True,
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
    receipt_number = models.CharField(max_length=50, null=True, blank=True, unique=True, db_index=True, help_text="Unique receipt/reference number for this sale")
    
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

    def generate_receipt_number(self):
        """Generate a unique continuous receipt number in format: REC-XXXXX"""
        # Get the total count of all receipts with receipt_number set
        total_count = Withdrawals.objects.filter(
            receipt_number__isnull=False
        ).count() + 1
        
        receipt_num = f"REC-{total_count:06d}"
        return receipt_num

    def save(self, *args, **kwargs):
        """Auto-generate receipt number if not already set"""
        if not self.receipt_number:
            self.receipt_number = self.generate_receipt_number()
        super().save(*args, **kwargs)

    @staticmethod
    def get_queryset(request):
        query = request.GET.get("q")
        qs = Withdrawals.objects.all().order_by("-date")
        if query:
            qs = qs.filter(
                Q(reason__icontains=query) |
                Q(item_type__icontains=query) |
                Q(receipt_number__icontains=query)
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